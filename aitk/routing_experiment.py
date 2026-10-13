"""The D11 experiment: the independent reviewer runs one allowlisted test.

Phase 6 measures whether a reviewer that may run one targeted test changes what
the verifier lane finds. `bin/aitk model-run --experiment reviewer-runs-test
--test-command <command>` turns it on for one dispatch of a boundary whose
contract is `agents/specialists/reviewer.md`; without the flag nothing here
runs. Delete this module and the flag once D11 is settled.

The reviewer gets three things, and nothing else changes about its lane:

- An allowlist of test commands, taken only from `--test-command`
  (`experiment`): nothing in the reviewed tree can add to it.
- A disposable scratch copy of its worktree (`scratch_copy`), which becomes the
  worker's workspace and the only place its commands may write. The source
  worktree is never the worker's directory, and the copy is removed after the
  run.
- Provider controls that hold the allowlist and the copy:
  - Claude: `dontAsk` with one `Bash(<entry>)` allow rule per entry beside the
    route's read-only git rules, so any other command is denied, and the Bash
    sandbox (`CLAUDE_SANDBOX_SETTINGS`) confining writes to the copy with no
    network and no unsandboxed retry.
  - Codex has no command allowlist, so there the allowlist is an instruction;
    the `workspace-write` sandbox rooted at the copy, with no network and with
    neither `/tmp` nor `$TMPDIR` writable, under `approval_policy="never"`, is
    the boundary (`CODEX_SANDBOX_CONFIG`).

An entry is a test command written as plain words. `npm test` allows exactly
that command. An entry ending in ` *` is a prefix: `python3 -m pytest *` allows
the words before the `*` followed by more words, which is how the reviewer names
the one test to run. A test runner given arbitrary arguments can still run
arbitrary code, which is why the scratch copy and the sandbox, not the
allowlist, are the write and network boundary.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from aitk.routing_policy import ModelRouteError, ResolvedRoute


REVIEWER_RUNS_TEST = "reviewer-runs-test"


EXPERIMENTS = (REVIEWER_RUNS_TEST,)


# The contract that marks the independent reviewer's boundaries
# (`review.independent`, `review.second-family`, `review.delta` and the PR
# variants). No other lane may run a test under the experiment.
REVIEWER_CONTRACT = "agents/specialists/reviewer.md"


MAX_TEST_COMMANDS = 8


MAX_TEST_COMMAND_LENGTH = 200


# One word of an allowlist entry: no quotes, `$`, backquotes, globs, `~`,
# parentheses, redirections or shell operators, so the entry is one command and
# cannot close the `Bash(...)` rule it becomes.
_WORD = re.compile(r"[A-Za-z0-9_@%+=:,./-]+")


# Programs that run their arguments as another command. A prefix entry may not
# start with one, or `timeout 60 *` would allow any command at all.
COMMAND_RUNNERS = frozenset(
    {
        "sh", "bash", "zsh", "dash", "ksh", "fish",
        "env", "xargs", "exec", "eval", "command", "builtin", "nohup", "nice",
        "timeout", "time", "stdbuf", "setsid", "ionice", "flock", "watch",
        "sudo", "doas", "su", "docker", "podman", "kubectl", "ssh",
    }
)


# The Bash sandbox a Claude reviewer runs its commands in (`--settings`, which
# `--restricted` still loads). Writes go only to the working directory (the
# scratch copy) and Claude Code's per-user temp directory, which
# `CLAUDE_CODE_TMPDIR` puts inside the scratch root. `failIfUnavailable` makes a
# missing sandbox a startup error instead of an unsandboxed run, no command may
# retry outside it, an empty allowlist with `strictAllowlist` refuses every
# host, and with auto-allow off a sandboxed command still needs an allow rule.
CLAUDE_SANDBOX_SETTINGS: dict[str, object] = {
    "sandbox": {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "autoAllowBashIfSandboxed": False,
        "network": {"allowedDomains": [], "strictAllowlist": True},
    }
}


CLAUDE_PERMISSION_MODE = "dontAsk"


CODEX_SANDBOX = "workspace-write"


# `codex exec` overrides for the experiment; the scratch temp directory is added
# as the one writable root besides the `--cd` workspace.
CODEX_SANDBOX_CONFIG = (
    'approval_policy="never"',
    "sandbox_workspace_write.network_access=false",
    "sandbox_workspace_write.exclude_slash_tmp=true",
    "sandbox_workspace_write.exclude_tmpdir_env_var=true",
)


# How each provider holds the allowlist, recorded in the envelope so the D11
# measurement can tell the two apart.
ENFORCEMENT = {
    "claude": "permission-rules+sandbox",
    "codex": "instruction+sandbox",
}


# What git reads to find a repository other than the working directory
# (`git rev-parse --local-env-vars`). They are dropped from the environment of
# the copy's git calls and of the worker, so neither can reach the source repo.
_GIT_REPOSITORY_ENV = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
)


_GIT_TIMEOUT = 300


@dataclass(frozen=True)
class Experiment:
    name: str
    test_commands: tuple[str, ...]

    def record(self, provider: str) -> dict[str, object]:
        """The envelope's `experiment` field: what ran and what was allowed."""
        return {
            "name": self.name,
            "allowed_commands": list(self.test_commands),
            "enforcement": ENFORCEMENT[provider],
        }


@dataclass(frozen=True)
class Scratch:
    root: Path
    worktree: Path
    temp: Path


def _command_problem(command: str) -> str | None:
    if len(command) > MAX_TEST_COMMAND_LENGTH:
        return f"is longer than {MAX_TEST_COMMAND_LENGTH} characters"
    words = command.split(" ")
    prefix = words[-1] == "*"
    if prefix:
        words = words[:-1]
    if not words or not all(_WORD.fullmatch(word) for word in words):
        return (
            "must be plain words separated by single spaces, optionally ending in "
            "' *': no quotes, variables, globs, redirections or shell operators"
        )
    if not prefix:
        return None
    if len(words) < 2:
        return (
            "is a one-word prefix; name the program and its test command, as in "
            "'npm test *' or 'python3 -m pytest *'"
        )
    if words[-1].startswith("-"):
        return "ends its prefix in an option, which would let any value follow it"
    if os.path.basename(words[0]) in COMMAND_RUNNERS:
        return f"starts with {words[0]}, which runs its arguments as another command"
    return None


def experiment(name: str | None, test_commands: Sequence[str]) -> Experiment | None:
    """Validate `--experiment` and its `--test-command` allowlist."""
    if name is None:
        if test_commands:
            raise ModelRouteError(
                f"--test-command is only accepted with --experiment {REVIEWER_RUNS_TEST}"
            )
        return None
    if name not in EXPERIMENTS:
        raise ModelRouteError(f"unknown experiment: {name}")
    if not test_commands:
        raise ModelRouteError(
            f"--experiment {name} needs at least one --test-command: the allowlist "
            "of test commands the reviewer may run"
        )
    if len(test_commands) > MAX_TEST_COMMANDS:
        raise ModelRouteError(f"at most {MAX_TEST_COMMANDS} --test-command entries")
    for command in test_commands:
        problem = _command_problem(command)
        if problem is not None:
            raise ModelRouteError(f"--test-command {command!r} {problem}")
    return Experiment(name, tuple(dict.fromkeys(test_commands)))


def reviewer_route(route: ResolvedRoute, chosen: Experiment) -> ResolvedRoute:
    """The route this experiment runs: the reviewer lane with its test rules.

    Only the controls the experiment needs change: Claude moves from `plan` to
    `dontAsk` and gains a `Bash(<entry>)` rule per allowlist entry; Codex moves
    from `read-only` to `workspace-write`, rooted at the scratch copy.
    """
    if REVIEWER_CONTRACT not in route.required_contracts or route.responsibility != "review":
        raise ModelRouteError(
            f"--experiment {chosen.name} applies only to the independent reviewer's "
            f"boundaries (those whose contract is {REVIEWER_CONTRACT}); "
            f"{route.boundary} is not one"
        )
    controls = dict(route.controls)
    if route.provider == "claude":
        controls["permission_mode"] = CLAUDE_PERMISSION_MODE
    else:
        controls["sandbox"] = CODEX_SANDBOX
    rules = tuple(f"Bash({command})" for command in chosen.test_commands)
    return replace(route, controls=controls, tools=route.tools + rules)


def instruction_lines(chosen: Experiment) -> str:
    """The experiment's lines in the worker's dispatch header."""
    return (
        f"experiment={chosen.name}\n"
        f"allowed_test_commands={json.dumps(list(chosen.test_commands))}\n"
        "experiment_rule=Unlike the contract's read-only rule, this dispatch may run "
        "one targeted test: one of allowed_test_commands exactly as written, where an "
        'entry ending in " *" takes the test to run as plain words in place of the '
        '"*". Run it from the workspace, a disposable copy of the reviewed tree. Run '
        "no other command beyond the route's read-only git commands: no shell, "
        "install, network access or file edit. Put the command you ran and its "
        "result in verification.\n"
    )


def worker_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """The worker's environment without git's repository variables."""
    source = dict(os.environ if base is None else base)
    return {key: value for key, value in source.items() if key not in _GIT_REPOSITORY_ENV}


def claude_environment(scratch: Scratch) -> dict[str, str]:
    """A Claude worker's environment: its temp directory inside the scratch root,
    and credentials scrubbed from the commands it runs."""
    environment = worker_environment()
    environment["CLAUDE_CODE_TMPDIR"] = str(scratch.temp)
    environment["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = "1"
    return environment


def _git(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        text=True,
        capture_output=True,
        timeout=_GIT_TIMEOUT,
        check=False,
        env=worker_environment(),
    )


def _git_value(directory: Path, *arguments: str) -> str | None:
    result = _git(directory, *arguments)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def source_commit(source: Path) -> str | None:
    """The commit the copy starts from, or None outside git or before a commit.

    The copy is of the whole worktree, so a source inside a repository must be
    the top of its worktree: a subdirectory would hand the reviewer a tree that
    cannot run the project's tests.
    """
    try:
        top = _git_value(source, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ModelRouteError(f"git could not inspect {source}: {error}") from error
    if top is None:
        return None
    if Path(top).resolve() != source.resolve():
        raise ModelRouteError(
            f"--experiment {REVIEWER_RUNS_TEST} copies the whole worktree; pass "
            f"--cwd {top}, the top of the worktree, not a directory inside it"
        )
    return _git_value(source, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")


def _skip(source: Path):
    """copytree's ignore: the source's own `.git`, and anything that is not a
    directory, regular file or symlink (sockets and pipes cannot be copied)."""

    def ignore(directory: str, names: list[str]) -> list[str]:
        skipped = []
        for name in names:
            if Path(directory) == source and name == ".git":
                skipped.append(name)
                continue
            try:
                mode = os.lstat(os.path.join(directory, name)).st_mode
            except OSError:
                skipped.append(name)
                continue
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
                skipped.append(name)
        return skipped

    return ignore


def _copy_worktree(source: Path, destination: Path) -> None:
    """Copy the worktree as it stands, uncommitted and untracked files included.

    In a repository the copy is a standalone clone that borrows the source's
    objects read-only (`--shared`), detached at the source's commit with its
    index at that commit, so `git diff` and `git log` in the copy show what they
    show in the source. It is never a linked worktree: Claude's sandbox lets a
    linked worktree write its main repository's `.git`. The clone keeps no
    remote, so nothing in the copy points back at the source to push to.
    """
    commit = source_commit(source)
    if commit is not None:
        result = _git(
            source, "clone", "--quiet", "--shared", "--no-checkout", "--",
            str(source), str(destination),
        )
        if result.returncode:
            raise ModelRouteError(f"git clone failed: {result.stderr.strip()[:300]}")
        for arguments in (
            ("remote", "remove", "origin"),
            ("update-ref", "--no-deref", "HEAD", commit),
            ("read-tree", commit),
        ):
            result = _git(destination, *arguments)
            if result.returncode:
                raise ModelRouteError(
                    f"git {arguments[0]} failed in the copy: {result.stderr.strip()[:300]}"
                )
    try:
        shutil.copytree(
            source, destination, symlinks=True, ignore=_skip(source), dirs_exist_ok=True
        )
    except shutil.Error as error:
        raise ModelRouteError(f"the worktree could not be copied: {error}") from error


def _remove(root: Path) -> None:
    """Remove the scratch root, including directories a test left read-only."""
    shutil.rmtree(root, ignore_errors=True)
    if not os.path.lexists(root):
        return
    for directory, names, _files in os.walk(root):
        for name in names:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                try:
                    os.chmod(path, 0o700)
                except OSError:
                    pass
    shutil.rmtree(root, ignore_errors=True)


@contextmanager
def scratch_copy(source: Path) -> Iterator[Scratch]:
    """A private scratch root holding a copy of `source` and a temp directory."""
    root = Path(tempfile.mkdtemp(prefix="aitk-rt-")).resolve()
    try:
        os.chmod(root, 0o700)
        scratch = Scratch(root=root, worktree=root / "worktree", temp=root / "tmp")
        scratch.temp.mkdir(mode=0o700)
        _copy_worktree(source, scratch.worktree)
        yield scratch
    finally:
        _remove(root)
