"""hooks/pre-push-validate.sh: blocks a push on failed checks and warns on overdue ones.

Each case runs the hook with a synthetic PreToolUse payload against a scratch
repository whose `origin/main` is behind HEAD, with stub `pre-commit` and
`pytest` executables and a PATH built from symlinks, so the result does not
depend on what the machine has installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "pre-push-validate.sh"
# No `timeout` or `gtimeout`: the hook enforces its budgets with its own watchdog
# and never calls either, so the suite runs the same on a host without them.
TOOLS = ("bash", "cat", "dirname", "env", "git", "mktemp", "python3", "rm", "sleep")
GRACE = int(re.search(r"^GRACE=(\d+)$", HOOK.read_text(), re.M).group(1))

STUB = """#!/bin/bash
case "${{{variable}:-pass}}" in
    fail) echo "{name}: 1 problem found" >&2; exit 1 ;;
    sleep) exec sleep 30 ;;
    sigkill) kill -9 $$ ;;
    exit124) exit 124 ;;
    stubborn) trap '' TERM; exec sleep 30 ;;
    fork) sleep 30 & echo $! > "$GRANDCHILD_PIDFILE"; wait ;;
    forkstubborn) (trap '' TERM; exec sleep 30) & echo $! > "$GRANDCHILD_PIDFILE"; wait ;;
    forkfail) sleep 30 & echo $! > "$GRANDCHILD_PIDFILE"; exit 1 ;;
    termexit200) trap '' TERM; sleep 3; exit 200 ;;
    termexit137) trap '' TERM; sleep 3; exit 137 ;;
    termexit143) trap '' TERM; sleep 3; exit 143 ;;
    termexit0) trap 'exit 0' TERM; sleep 30 & wait ;;
    termexit1) trap '' TERM; sleep 3; exit 1 ;;
    termsignal) trap 'kill -USR1 $$' TERM; sleep 30 & wait ;;
    termgroupsignal) trap 'kill -USR1 0' TERM; sleep 30 & wait ;;
    hookfailthensleep)
        echo "ruff..................................................................Failed" >&2
        echo "- hook id: ruff" >&2
        echo "- exit code: 1" >&2
        exec sleep 30 ;;
    hookpassthensleep)
        echo "ruff..................................................................Passed" >&2
        exec sleep 30 ;;
    markerfail) : > "$FIXED_MARKER"; exit 1 ;;
    stdin) [ /dev/stdin -ef /dev/null ] || {{ echo "{name}: stdin is not /dev/null" >&2; exit 1; }} ;;
esac
exit 0
"""


def git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.com", "-c", "user.name=Test", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


class PrePushHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        base = Path(cls.temporary.name).resolve()
        origin = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        cls.repo = base / "work"
        cls.repo.mkdir()
        git(cls.repo, "init", "-q", "-b", "main")
        (cls.repo / "README.md").write_text("readme\n")
        (cls.repo / ".pre-commit-config.yaml").write_text("repos: []\n")
        git(cls.repo, "add", "README.md", ".pre-commit-config.yaml")
        git(cls.repo, "commit", "-q", "-m", "base")
        git(cls.repo, "remote", "add", "origin", str(origin))
        git(cls.repo, "push", "-q", "-u", "origin", "main")
        (cls.repo / "app.py").write_text("VALUE = 1\n")
        (cls.repo / "tests").mkdir()
        (cls.repo / "tests" / "test_app.py").write_text("def test_value():\n    assert True\n")
        git(cls.repo, "add", "app.py", "tests/test_app.py")
        git(cls.repo, "commit", "-q", "-m", "change")

        # The repo's pinned pytest, untracked.
        venv_bin = cls.repo / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        cls.write_stub(venv_bin / "pytest", "STUB_PYTEST", "pytest")

        cls.stubs = base / "stubs"
        cls.stubs.mkdir()
        cls.write_stub(cls.stubs / "pre-commit", "STUB_PRECOMMIT", "pre-commit")
        cls.bins: dict[tuple[str, ...], Path] = {}
        cls.base = base

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @staticmethod
    def write_stub(path: Path, variable: str, name: str) -> None:
        path.write_text(STUB.format(variable=variable, name=name))
        path.chmod(0o755)

    def tool_dir(self, tools: tuple[str, ...]) -> Path:
        if tools not in self.bins:
            directory = Path(tempfile.mkdtemp(dir=self.base, prefix="bin-"))
            for tool in tools:
                found = shutil.which(tool)
                if found is None:
                    self.skipTest(f"{tool} is not installed")
                os.symlink(found, directory / tool)
            self.bins[tools] = directory
        return self.bins[tools]

    def run_hook(
        self,
        command: str,
        *,
        stubs: bool = True,
        tools: tuple[str, ...] = TOOLS,
        front: tuple[Path, ...] = (),
        cwd: Path | None = None,
        **env: str,
    ) -> subprocess.CompletedProcess[str]:
        path = [str(self.tool_dir(tools))]
        if stubs:
            path.insert(0, str(self.stubs))
        path[:0] = [str(directory) for directory in front]
        environment = {"PATH": os.pathsep.join(path), "HOME": str(self.base), **env}
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd or self.repo)})
        return subprocess.run(
            [shutil.which("bash"), str(HOOK)],
            input=payload,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
            timeout=120,
        )

    def assert_blocked(self, result: subprocess.CompletedProcess[str], reason: str) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED: pre-push validation failed", result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        self.assertNotIn("SKIP_PRECHECK", result.stderr)
        self.assertEqual("", result.stdout)

    def test_other_commands_exit_quietly(self) -> None:
        for command in ("git status", "echo push", "git log --oneline", "ls"):
            with self.subTest(command=command):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_a_push_behind_a_wrapper_the_tokenizer_does_not_know_is_validated(self) -> None:
        for command in (
            "setsid git push origin main",
            "flock /tmp/x git push",
            "uv run git push",
            "flock /tmp/git git push",
            "find . -name git -exec git push \\;",
            # a git-* head git does not install is an ordinary executable, rescanned like any
            "./git-run git push --force origin main",
            "git-x sh -c 'git push origin main'",
            "/opt/x/git-wrap env git push origin main",
            "git-wrap git push",
            # the fast exit reads the word as the parser does: quoting removed
            "git pu'sh' origin main",
            "git pu\\\nsh origin main",
        ):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")

    def assert_unknown_repository(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn("cannot tell which repository this push runs in; run it directly", result.stderr)
        self.assertIn("stop and ask the user", result.stderr)
        self.assertNotIn("SKIP_PRECHECK", result.stderr)
        self.assertEqual("", result.stdout)

    def assert_unreadable(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assert_unknown_repository(result)
        self.assertIn("could not be read in full", result.stderr)

    def test_text_git_runs_that_mentions_a_push_blocks_on_sight(self) -> None:
        # Nothing git runs is resolved: an inline alias in the segment, or the words after
        # `rebase -x`, `bisect run` or `submodule foreach`, that mention a push make the
        # command unreadable, whatever the alias or the text really is. The caller's checks
        # would pass here (clean stub) or fail (STUB_PRECOMMIT=fail): neither is consulted.
        filler = " ".join(f"GIT_CONFIG_KEY_{n}=core.x{n} GIT_CONFIG_VALUE_{n}=v" for n in range(100))
        for command in (
            "git bisect run sh -c 'git push'",
            "git bisect run \"git''\" push",
            "git rebase -x 'git push' HEAD~1",
            "git rebase --exec='git push' HEAD~1",
            # a backslash-newline is joined before the word is read, as mentions_gated does
            "git rebase -x 'git pu\\\nsh' HEAD~1",
            "git -c 'alias.x=!git pu\\\nsh origin feature' x",
            "git -c alias.x='!git pu\\\nsh' x",
            "git rebase -ix 'git push' HEAD~1",
            "git submodule foreach git push",
            "git submodule foreach --recursive 'git push'",
            "git submodule foreach sh -c 'git push'",
            f"git -C {self.repo} submodule foreach git push",
            "git -c alias.x='!git' x push",
            "git -c alias.x='!git push' x",
            "git -c alias.x=y -c alias.y='!git' x push",
            "git -c alias.p=push p origin main",
            "git -c alias.p=push -c alias.q=p q",
            "git -c alias.p='push origin' p main",
            "git -calias.p=push p",
            "P=push git --config-env=alias.p=P p",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push git p",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push setsid git p",
            "git -c alias.p=push -c alias.x='!flock /tmp/x git p' x",
            "git -c alias.p=push -c alias.x='!env GIT_CONFIG_COUNT=0 git p' x",
            "git -c alias.rebase=status rebase -x 'git push' HEAD~1",
            "git -c alias.rebase='!true' rebase -x 'git push' HEAD~1",
            f"GIT_CONFIG_COUNT=101 {filler} GIT_CONFIG_KEY_100=alias.p GIT_CONFIG_VALUE_100=push git p",
            "git -c alias.x=y -c alias.y=x x push",
            # a segment the work budget could not cover is unreadable too
            "true " + "sh " * 4000 + "git push",
            "true " + "sh " * 4000 + "; git -c alias.x=\"!git pu'sh'\" x # push",
            # a plain word `push` is enough (an accepted over-block)
            "git bisect run ./push.sh",
            # a dashed entry point hands text on like the subcommand it names
            "git-rebase -x 'git push' HEAD~1",
            "git-bisect run sh -c 'git push'",
            "git-submodule foreach git push",
            "git submodule--helper foreach git push",
            "git-config alias.p push",
            "git config alias.p push",
            "git --attr-source HEAD rebase -x 'git push' HEAD~1",
        ):
            with self.subTest(command=command[:80]):
                self.assert_unreadable(self.run_hook(command))
                self.assert_unreadable(self.run_hook(command, STUB_PRECOMMIT="fail"))
        # only the user's session bypass lifts it
        self.assertEqual(0, self.run_hook("git submodule foreach git push", SKIP_PRECHECK="1").returncode)

    def test_an_unreadable_command_that_mentions_no_push_does_not_block(self) -> None:
        # The command is unreadable (two aliases that loop, a budget spent) but no push is in
        # its text; `echo pushed` is no `push` word and a later plain command is read normally.
        for command in (
            "git -c alias.x=y -c alias.y=x x; echo pushed",
            "git -c alias.st=status st",
            "git -c alias.p=pull p origin main",
            "git rebase -x 'make test' HEAD~1; echo pushed",
            "git bisect run ./t.sh \"it's\"; echo pushed",
            "git submodule foreach ./t.sh \"it's\"; echo pushed",
            "git submodule foreach 'echo $name'; echo pushed",
            "true " + "sh " * 4000 + "; echo pushed",
        ):
            with self.subTest(command=command[:80]):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_a_push_in_an_unknown_repository_blocks_instead_of_using_the_callers(self) -> None:
        other = self.base / "elsewhere"
        for command in (
            # another repository named by --git-dir, --work-tree or the variables
            f"git --git-dir={other}/.git push",
            f"git --work-tree={other} push origin main",
            f"GIT_DIR={other}/.git git push",
            f"env GIT_WORK_TREE={other} git push",
            # more -C hops than the tokenizer follows
            "git " + "-C . " * 17 + "push",
        ):
            with self.subTest(command=command[:80]):
                # the repository is clean here, and the caller's checks would pass
                self.assert_unknown_repository(self.run_hook(command))
                self.assert_unknown_repository(self.run_hook(command, STUB_PRECOMMIT="fail"))
        self.assertEqual(0, self.run_hook(f"git --git-dir={other}/.git push", SKIP_PRECHECK="1").returncode)
        # a directory that does not exist names no repository, so it is unknown too: `~` and
        # `$VAR` are read literally here, and skipping the checks would let the push through
        for command in (
            "git -C ~/x push",
            "git -C ~ push origin main",
            "git -C $DIR push",
            'git -C "$HOME/work" push',
            "git -C ${DIR}/work push origin main",
            f"git -C {other} push",
            f"git -C {self.repo}/missing push",
            f"git -C {other}/x -C ../y push",
        ):
            with self.subTest(command=command[:80]):
                self.assert_unknown_repository(self.run_hook(command))
                self.assert_unknown_repository(self.run_hook(command, STUB_PRECOMMIT="fail"))
        self.assertEqual(0, self.run_hook("git -C ~/x push", SKIP_PRECHECK="1").returncode)
        # a value the shell expands is unknown before any path arithmetic: `"$X/.."` and `~/..`
        # collapse to the caller's directory, a folder literally named `$DIR` exists in the repo
        # (the shell expands it to another repository), and a newline cuts the line-based read
        literal = self.repo / "$DIR"
        literal.mkdir(exist_ok=True)
        self.addCleanup(literal.rmdir)
        newline = self.repo / "nl\nsub"
        newline.mkdir(exist_ok=True)
        self.addCleanup(newline.rmdir)
        for command in (
            'git -C "$OTHER/.." push',
            "git -C ~/.. push",
            "git -C '~/..' push",
            "git -C '$DIR' push",
            'git -C "$DIR" push origin main',
            "git -C '$DIR/..' push",
            "git -C 'nl\nsub' push",
            "git -C 'nl\nsub/..' push",
            f"git -C {self.repo}/sub -C '$DIR' push",
            'cd "$OTHER/.." && git push',
            "cd '$DIR' && git push",
            "cd $DIR && git push",
            'cd "`pwd`/.." && git push',
            "cd 'nl\nsub' && git push",
            "env -C '$DIR' git push",
            "git push && cd '$DIR' && git push",
        ):
            with self.subTest(command=command[:80]):
                self.assert_unknown_repository(self.run_hook(command))
                self.assert_unknown_repository(self.run_hook(command, STUB_PRECOMMIT="fail"))
        self.assertEqual(0, self.run_hook('git -C "$OTHER/.." push', SKIP_PRECHECK="1").returncode)
        # a session directory whose name holds a newline would be cut short by the line-based read
        # below (and then skipped as not a directory): it is unknown too
        self.assert_unknown_repository(self.run_hook("git push", cwd=newline))
        self.assert_unknown_repository(self.run_hook("git push", cwd=newline, STUB_PRECOMMIT="fail"))
        # a known directory is still validated; `-C` is followed lexically (normpath)
        (self.repo / "sub").mkdir(exist_ok=True)
        for command in (
            "git push",
            # a global option with a separate value, and a dashed entry point, are the push
            "git --attr-source HEAD push origin main",
            "git --super-prefix x/ push",
            "git-push origin main",
            "$(git --exec-path)/git-push origin main",
            "/usr/lib/git-core/git-push origin main",
            "setsid git-push origin main",
            # a bare `alias.NAME` word is a name: a normal push, not an unreadable command
            "git push origin alias.cleanup",
            "git-push origin alias.cleanup",
            f"git -C {self.repo} push",
            f"git -C {self.repo}/sub/.. push",
            "git -C sub push",
            "git -C sub/.. push",
            'git -C "" push',
            "git -C . push",
            "cd sub && git push",
            "git " + "-C . " * 16 + "push",
            # an unreadable segment without a push word does not hide a later plain push
            "true " + "sh " * 4000 + "; git push origin main",
        ):
            with self.subTest(command=command[:80]):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")
        # accepted limit: a symlink in a `-C` path is not resolved, so `deep-link/..` is the
        # link's parent (no repository), not the link target's parent, and nothing is checked
        aux = self.base / "aux"
        aux.mkdir(exist_ok=True)
        (aux / "deep-link").symlink_to(self.repo / "sub")
        result = self.run_hook(f"git -C {aux}/deep-link/.. push", STUB_PRECOMMIT="fail")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_the_documented_over_blocks_are_pinned(self) -> None:
        # Accepted: a later argument that names a git entry point restarts the scan and is read
        # as that command (after an unknown wrapper it cannot be told from a command), an
        # executable named like one is that command, and text that only mentions a push next
        # to an alias or in the words git runs is unreadable. None of these pushes anything.
        for command in (
            "chmod +x bin/git-push",
            "make git-push",
            "uv run pytest tests/git-push",
            "./git-push origin main",
            "git --exec-path push",
        ):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")
        for command in ("git config --get alias.push", "git grep alias.x=1 push"):
            with self.subTest(command=command):
                self.assert_unreadable(self.run_hook(command))
        # Accepted limit (a real push this hook does not see): git reached through a variable.
        # The git guard reads `G=git-push; $G -f origin main`; this hook does not resolve `$G`.
        for command in ("G=git-push; $G origin main", "G=git-push\n$G -f origin main", "G=git; $G push origin main"):
            with self.subTest(command=command):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)
        # a git-* name git does not install is not an entry point, so it is read as an argument
        # only where it follows a rescan word; as a head on its own it is an executable
        for command in ("git-run origin main", "./git-lfs push", "git-x --force"):
            with self.subTest(command=command):
                result = self.run_hook(command, STUB_PRECOMMIT="fail")
                self.assertEqual(0, result.returncode, result.stderr)

    def test_matching_an_unreadable_command_for_a_push_is_linear(self) -> None:
        # `\bgit\b.*\bpush\b` retried from every `git` word across the rest of ~160 KB
        # with no push after them: quadratic. The payload does not tokenize, so it is
        # matched as text.
        text = 'bash -c "push ' + "git " * 40000 + "'\""
        started = time.monotonic()
        result = self.run_hook(text, STUB_PRECOMMIT="fail")
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(0, result.returncode, result.stderr)
        # a push after the git words in unresolved text is still found: validated in the
        # caller's directory, or unknown when the text changes directory
        text = 'bash -c "' + "git " * 40000 + "git push origin main '\""
        started = time.monotonic()
        result = self.run_hook(text, STUB_PRECOMMIT="fail")
        self.assertLess(time.monotonic() - started, 5.0)
        self.assert_blocked(result, "pre-commit failed")
        self.assert_unknown_repository(self.run_hook('bash -c "' + "git " * 40000 + "-C . push '\""))

    def test_fused_operator_runs_do_not_hide_a_push(self) -> None:
        # shlex fuses `;(` and `&&(` into one token: the push after the run read as
        # arguments and the hook exited. The run is split into its operators now.
        for command in (
            "git fetch;(git push -f origin main)",
            "git status&&(git push --force origin main)",
            "true;{ git push origin main; }",
            "git status||(git push origin main)",
        ):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")

    def test_the_head_is_read_without_case(self) -> None:
        for command in ("GIT push origin main", "Git-push origin main", "env GIT push", "/usr/bin/GIT push"):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")

    def test_for_each_repo_hands_git_a_command(self) -> None:
        for command in (
            "git -c x.r=. for-each-repo --config=x.r push -f origin main",
            "git for-each-repo --config x.r push --force",
            "git for-each-repo --keep-going --config=x.r push",
        ):
            with self.subTest(command=command):
                self.assert_unreadable(self.run_hook(command))
                self.assert_unreadable(self.run_hook(command, STUB_PRECOMMIT="fail"))
        # without a push in its text it is an ordinary command
        result = self.run_hook("git for-each-repo --config=x.r maintenance run", STUB_PRECOMMIT="fail")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_tab_or_glob_in_a_directory_leaves_the_repository_unknown(self) -> None:
        glob = self.repo / "[w]ork"
        glob.mkdir(exist_ok=True)
        self.addCleanup(glob.rmdir)
        tabbed = self.repo / "tab\t"
        tabbed.mkdir(exist_ok=True)
        self.addCleanup(tabbed.rmdir)
        for command in (
            f"git -C '{self.repo}/[w]ork' push",
            f"git -C '{self.repo}/w*' push",
            f"git -C '{self.repo}/?' push",
            f"git -C '{self.repo}/tab\t' push",
            f"cd '{self.repo}/[w]ork' && git push",
            f"cd '{self.repo}/tab\t' && git push",
        ):
            with self.subTest(command=command):
                self.assert_unknown_repository(self.run_hook(command))
                self.assert_unknown_repository(self.run_hook(command, STUB_PRECOMMIT="fail"))
        # a session directory that ends in a tab is refused too: `read` would strip it
        self.assert_unknown_repository(self.run_hook("git push", cwd=tabbed))
        self.assert_unknown_repository(self.run_hook("git push", cwd=tabbed, STUB_PRECOMMIT="fail"))

    def test_cd_to_the_git_toplevel_follows_the_repository(self) -> None:
        sub = self.repo / "sub"
        sub.mkdir(exist_ok=True)
        for command in (
            'cd "$(git rev-parse --show-toplevel)" && git push',
            "cd $(git rev-parse --show-toplevel) && git push",
            "cd `git rev-parse --show-toplevel` && git push",
        ):
            with self.subTest(command=command):
                # the toplevel is the repository, so its checks run (and block here)
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail", cwd=sub), "pre-commit failed")
                self.assertEqual(0, self.run_hook(command, cwd=sub).returncode)
        # any other substitution stays unknown
        for command in (
            'cd "$(git rev-parse --show-cdup)" && git push',
            'cd "$(git rev-parse --show-toplevel)/.." && git push',
            'cd "$(pwd)" && git push',
        ):
            with self.subTest(command=command):
                self.assert_unknown_repository(self.run_hook(command, cwd=sub))

    def test_the_parser_blocks_when_it_runs_out_of_time(self) -> None:
        script = HOOK.read_text()
        parser = re.search(r"read -r -d '' PARSER <<'PY'\n(.*?)\nPY\n", script, re.S).group(1)
        self.assertIn("DEADLINE = 15.0", parser)
        payload = json.dumps({"tool_input": {"command": "git push " + "sh " * 200000}, "cwd": str(self.repo)})
        environment = {**os.environ, "PYTHONPATH": str(ROOT)}
        # an expired deadline reads as an unreadable command ...
        expired = subprocess.run(
            ["python3", "-c", parser.replace("DEADLINE = 15.0", "DEADLINE = 0.05")],
            input=payload, text=True, capture_output=True, env=environment, cwd=ROOT, check=False,
        )
        self.assertEqual(0, expired.returncode, expired.stderr)
        self.assertEqual("unreadable\t", expired.stdout.strip("\n"))
        # ... which the hook turns into a block unless the user skips the checks
        copy = self.base / "deadline-copy"
        (copy / "hooks").mkdir(parents=True, exist_ok=True)
        if not (copy / "aitk").exists():
            (copy / "aitk").symlink_to(ROOT / "aitk")
        patched = copy / "hooks" / "pre-push-validate.sh"
        patched.write_text(script.replace("DEADLINE = 15.0", "DEADLINE = 0.05"))
        command = "git push " + "sh " * 200000
        result = subprocess.run(
            [shutil.which("bash"), str(patched)],
            input=json.dumps({"tool_input": {"command": command}, "cwd": str(self.repo)}),
            text=True, capture_output=True, check=False, timeout=120,
            env={"PATH": os.pathsep.join([str(self.stubs), str(self.tool_dir(TOOLS))]), "HOME": str(self.base)},
        )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn("could not be read in full", result.stderr)

    def test_the_git_value_flags_come_from_the_shared_tokenizer(self) -> None:
        script = HOOK.read_text()
        self.assertNotIn("GIT_VALUE_FLAGS = {", script)
        # the parser reads the flags through the shared git_globals, which holds the one set
        self.assertIn("shell_tokens.git_globals", script)

    def test_passing_checks_allow_the_push(self) -> None:
        result = self.run_hook("git push origin main")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_failed_checks_block_without_a_bypass_recipe(self) -> None:
        self.assert_blocked(self.run_hook("git push", STUB_PRECOMMIT="fail"), "pre-commit failed")
        self.assert_blocked(self.run_hook("git push", STUB_PYTEST="fail"), "pytest failed")
        self.assert_blocked(
            self.run_hook("cd . && timeout 60 git push origin main", STUB_PRECOMMIT="fail"),
            "pre-commit failed",
        )

    def assert_warned(self, result: subprocess.CompletedProcess[str], reason: str) -> None:
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("BLOCKED", result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(reason, context)
        self.assertIn("push proceeds", context)

    def test_a_check_past_its_budget_warns_and_allows(self) -> None:
        lint = self.run_hook("git push", STUB_PRECOMMIT="sleep", AITK_PRECHECK_LINT_BUDGET="2")
        self.assert_warned(lint, "pre-commit did not finish within 2s")
        tests = self.run_hook("git push", STUB_PYTEST="sleep", AITK_PRECHECK_TEST_BUDGET="2")
        self.assert_warned(tests, "pytest did not finish within 2s")

    def assert_overrun_ends_the_whole_tree(self, variable: str, mode: str, budget: str, reason: str) -> None:
        pidfile = Path(tempfile.mkdtemp(dir=self.base)) / "grandchild.pid"

        def reap() -> None:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except (ProcessLookupError, ValueError):
                    pass

        self.addCleanup(reap)
        started = time.monotonic()
        result = self.run_hook(
            "git push", GRANDCHILD_PIDFILE=str(pidfile), **{variable: mode, budget: "2"}
        )
        elapsed = time.monotonic() - started
        self.assert_warned(result, reason)
        self.assertLess(elapsed, 2 + GRACE + 5, "the hook waited on a surviving descendant")
        grandchild = int(pidfile.read_text())
        for _ in range(30):
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            self.fail("a descendant of the overdue check is still running")

    def test_an_overrun_ends_the_checks_descendants_too(self) -> None:
        for mode in ("fork", "forkstubborn"):
            self.assert_overrun_ends_the_whole_tree(
                "STUB_PRECOMMIT", mode, "AITK_PRECHECK_LINT_BUDGET", "pre-commit did not finish within 2s"
            )
            self.assert_overrun_ends_the_whole_tree(
                "STUB_PYTEST", mode, "AITK_PRECHECK_TEST_BUDGET", "pytest did not finish within 2s"
            )

    def test_an_early_failure_ends_the_checks_descendants_too(self) -> None:
        pidfile = Path(tempfile.mkdtemp(dir=self.base)) / "grandchild.pid"

        def reap() -> None:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except (ProcessLookupError, ValueError):
                    pass

        self.addCleanup(reap)
        started = time.monotonic()
        result = self.run_hook(
            "git push", STUB_PRECOMMIT="forkfail", GRANDCHILD_PIDFILE=str(pidfile),
            AITK_PRECHECK_LINT_BUDGET="2",
        )
        elapsed = time.monotonic() - started
        self.assert_blocked(result, "pre-commit failed")
        self.assertLess(elapsed, 2 + GRACE + 5, "the hook waited on a surviving descendant")
        grandchild = int(pidfile.read_text())
        for _ in range(30):
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            self.fail("a descendant of the failed check is still running")

    def test_a_term_ignoring_check_exiting_200_during_grace_blocks(self) -> None:
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                result = self.run_hook(
                    "git push", AITK_PRECHECK_LINT_BUDGET="2", AITK_PRECHECK_TEST_BUDGET="2",
                    **{variable: "termexit200"},
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)

    def test_a_term_handling_check_exiting_137_or_143_on_its_own_blocks(self) -> None:
        # Bash reports a signal death and an explicit `exit 143` with the same
        # status; only a check the watchdog actually killed is a budget warning.
        for stub in ("termexit137", "termexit143"):
            for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
                with self.subTest(stub=stub, check=variable):
                    result = self.run_hook(
                        "git push", AITK_PRECHECK_LINT_BUDGET="2", AITK_PRECHECK_TEST_BUDGET="2",
                        **{variable: stub},
                    )
                    self.assert_blocked(result, reason)
                    self.assertNotIn("did not finish within", result.stderr)

    def test_an_overdue_check_that_handles_term_and_exits_0_still_warns(self) -> None:
        lint = self.run_hook("git push", STUB_PRECOMMIT="termexit0", AITK_PRECHECK_LINT_BUDGET="2")
        self.assert_warned(lint, "pre-commit did not finish within 2s")
        tests = self.run_hook("git push", STUB_PYTEST="termexit0", AITK_PRECHECK_TEST_BUDGET="2")
        self.assert_warned(tests, "pytest did not finish within 2s")

    def test_an_overdue_check_killed_by_another_signal_blocks(self) -> None:
        # Only the watchdog's own TERM or KILL makes an overdue death a budget
        # warning; a check that aborts or crashes on a different signal failed.
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                result = self.run_hook(
                    "git push", AITK_PRECHECK_LINT_BUDGET="2", AITK_PRECHECK_TEST_BUDGET="2",
                    **{variable: "termsignal"},
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)

    def test_an_overdue_check_that_signals_its_whole_group_blocks(self) -> None:
        # The check answers the watchdog's TERM by signalling its process group with
        # something else, which takes the launcher down before it records anything. Only
        # a launcher that died from the watchdog's own TERM or KILL may warn without a record.
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                result = self.run_hook(
                    "git push", AITK_PRECHECK_LINT_BUDGET="2", AITK_PRECHECK_TEST_BUDGET="2",
                    **{variable: "termgroupsignal"},
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)

    def fake_launcher(self, body: str) -> Path:
        """A `python3` that stands in for the launcher only, and runs the real one otherwise."""
        directory = Path(tempfile.mkdtemp(dir=self.base))
        script = directory / "python3"
        script.write_text(
            f'#!/bin/bash\nif [[ "${{1:-}}" == -I ]]; then\n{body}\nfi\nexec "$REAL_PYTHON" "$@"\n'
        )
        script.chmod(0o755)
        return directory

    def test_a_record_the_launcher_left_malformed_or_missing_blocks(self) -> None:
        # The launcher's arguments are `-I -c CODE STATUS_PATH CHECK...`.
        real = shutil.which("python3") or ""
        for name, body, budget in (
            ("garbage on time", 'printf "garbage\\n" > "$4"\nexit 0', "60"),
            ("garbage overdue", 'trap "" TERM\nsleep 3\nprintf "garbage\\n" > "$4"\nexit 0', "2"),
            ("exit code without a record", "exit 0", "60"),
            ("record disagrees with a clean exit", 'printf "exit 3\\n" > "$4"\nexit 0', "60"),
        ):
            with self.subTest(case=name):
                result = self.run_hook(
                    "git push", front=(self.fake_launcher(body),), REAL_PYTHON=real,
                    AITK_PRECHECK_LINT_BUDGET=budget, AITK_PRECHECK_TEST_BUDGET=budget,
                )
                self.assert_blocked(result, "pre-commit failed")
                self.assertNotIn("did not finish within", result.stderr)

    def test_an_overdue_check_whose_end_could_not_be_recorded_blocks(self) -> None:
        # The launcher cannot write its status record (a directory sits where the
        # record, and the temporary file it is renamed from, go): with no record an overdue non-zero exit would read
        # as a killed check and warn, so the launcher exits with a sentinel that
        # blocks instead.
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                directory = Path(tempfile.mkdtemp(dir=self.base))
                marker = directory / "marker"
                (directory / "marker.status").mkdir()
                (directory / "marker.status.tmp").mkdir()
                mktemp = directory / "mktemp"
                mktemp.write_text('#!/bin/bash\necho "$FIXED_MARKER"\n')
                mktemp.chmod(0o755)
                result = self.run_hook(
                    "git push", front=(directory,), FIXED_MARKER=str(marker),
                    AITK_PRECHECK_LINT_BUDGET="2", AITK_PRECHECK_TEST_BUDGET="2",
                    **{variable: "termexit1"},
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)
                self.assertIn("could not record", result.stderr)

    def test_a_hook_failure_before_a_later_overrunning_hook_blocks(self) -> None:
        # pre-commit runs its remaining hooks after one fails: the failure stays
        # visible in its output when a later hook overruns the budget.
        result = self.run_hook("git push", STUB_PRECOMMIT="hookfailthensleep", AITK_PRECHECK_LINT_BUDGET="2")
        self.assert_blocked(result, "pre-commit failed")
        self.assertNotIn("did not finish within", result.stderr)
        self.assertIn("ruff", result.stderr)  # the tool's output still reaches the model
        passed = self.run_hook("git push", STUB_PRECOMMIT="hookpassthensleep", AITK_PRECHECK_LINT_BUDGET="2")
        self.assert_warned(passed, "pre-commit did not finish within 2s")

    def test_marker_creation_or_stale_marker_blocks_with_a_setup_reason(self) -> None:
        for mode in ("mktemp-fails", "stale-marker"):
            with self.subTest(mode=mode):
                directory = Path(tempfile.mkdtemp(dir=self.base))
                marker = directory / "marker"
                marker.write_text("")
                mktemp = directory / "mktemp"
                mktemp.write_text(
                    "#!/bin/bash\nexit 1\n" if mode == "mktemp-fails"
                    else '#!/bin/bash\necho "$FIXED_MARKER"\n'
                )
                mktemp.chmod(0o755)
                if mode == "stale-marker":
                    rm = directory / "rm"
                    rm.write_text("#!/bin/bash\nexit 0\n")
                    rm.chmod(0o755)
                result = self.run_hook(
                    "git push", front=(directory,), FIXED_MARKER=str(marker), STUB_PRECOMMIT="sigkill",
                )
                self.assert_blocked(result, "deadline marker")
                self.assertNotIn("pre-commit failed", result.stderr)
                self.assertNotIn("pytest failed", result.stderr)
                self.assertNotIn("did not finish within", result.stderr)

    def test_a_marker_present_with_an_early_exit_status_stays_a_failure(self) -> None:
        # The check leaves a deadline marker, then exits 1 without being signalled:
        # the race where it fails just as the watchdog fires. Only a signalled
        # death may count as a timeout.
        directory = Path(tempfile.mkdtemp(dir=self.base))
        marker = directory / "marker"
        mktemp = directory / "mktemp"
        mktemp.write_text('#!/bin/bash\n: > "$FIXED_MARKER"\necho "$FIXED_MARKER"\n')
        mktemp.chmod(0o755)
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                result = self.run_hook(
                    "git push", front=(directory,), FIXED_MARKER=str(marker), **{variable: "markerfail"}
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)

    def test_a_marker_that_cannot_be_cleared_blocks_instead_of_warning(self) -> None:
        directory = Path(tempfile.mkdtemp(dir=self.base))
        real_rm = shutil.which("rm")
        rm = directory / "rm"
        rm.write_text(
            '#!/bin/bash\nfor argument in "$@"; do\n    case "$argument" in *aitk-prepush*) exit 1 ;; esac\n'
            f'done\nexec "{real_rm}" "$@"\n'
        )
        rm.chmod(0o755)
        scratch = Path(tempfile.mkdtemp(dir=self.base))
        result = self.run_hook("git push", front=(directory,), TMPDIR=str(scratch), STUB_PRECOMMIT="sigkill")
        self.assert_blocked(result, "deadline marker")
        self.assertNotIn("pre-commit failed", result.stderr)
        self.assertNotIn("pytest failed", result.stderr)
        self.assertNotIn("did not finish within", result.stderr)

    def test_an_overrun_never_hides_a_real_failure(self) -> None:
        result = self.run_hook(
            "git push", STUB_PRECOMMIT="sleep", STUB_PYTEST="fail", AITK_PRECHECK_LINT_BUDGET="2"
        )
        self.assert_blocked(result, "pytest failed")
        self.assertIn("Warnings:", result.stderr)
        self.assertIn("pre-commit did not finish within 2s", result.stderr)

    def test_a_check_killed_after_the_grace_warns_and_allows(self) -> None:
        result = self.run_hook("git push", STUB_PRECOMMIT="stubborn", AITK_PRECHECK_LINT_BUDGET="2")
        self.assert_warned(result, "pre-commit did not finish within 2s")

    def assert_failed_early(self, stub: str) -> None:
        for variable, reason in (("STUB_PRECOMMIT", "pre-commit failed"), ("STUB_PYTEST", "pytest failed")):
            with self.subTest(check=variable):
                result = self.run_hook(
                    "git push",
                    AITK_PRECHECK_LINT_BUDGET="2",
                    AITK_PRECHECK_TEST_BUDGET="2",
                    **{variable: stub},
                )
                self.assert_blocked(result, reason)
                self.assertNotIn("did not finish within", result.stderr)

    def test_an_early_sigkill_is_a_failure_not_a_budget_warning(self) -> None:
        self.assert_failed_early("sigkill")

    def test_a_child_exit_124_is_a_failure_not_a_budget_warning(self) -> None:
        self.assert_failed_early("exit124")

    def test_budgets_fit_inside_the_hook_timeout_and_only_go_down(self) -> None:
        script = HOOK.read_text()
        lint = int(re.search(r"budget (\d+) \"\$\{AITK_PRECHECK_LINT_BUDGET", script).group(1))
        tests = int(re.search(r"budget (\d+) \"\$\{AITK_PRECHECK_TEST_BUDGET", script).group(1))
        grace = int(re.search(r"^GRACE=(\d+)$", script, re.M).group(1))
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
        outer = next(
            handler["timeout"]
            for group in hooks
            for handler in group["hooks"]
            if "pre-push-validate.sh" in handler["command"]
        )
        parse = float(re.search(r"^DEADLINE = ([\d.]+)$", script, re.M).group(1))
        self.assertLess(parse + lint + tests + 2 * grace, outer)
        function = re.search(r"^budget\(\) \{\n.*?^\}\n", script, re.M | re.S).group(0)
        for override, expected in (("", "180"), ("60", "60"), ("999", "180"), ("0", "180"), ("x", "180")):
            with self.subTest(override=override):
                result = subprocess.run(
                    ["bash", "-c", function + 'budget 180 "$1"', "budget", override],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertEqual(expected, result.stdout.strip())

    def test_skip_precheck_counts_only_from_the_session_environment(self) -> None:
        for command in (
            "SKIP_PRECHECK=1 git push origin main",
            "env SKIP_PRECHECK=1 git push",
            "git status && SKIP_PRECHECK=1 git push",
            "echo SKIP_PRECHECK=1; git push origin main",
            "SKIP_PRECHECK=1 true && git push",
            "git push # SKIP_PRECHECK=1",
            "SKIP_PRECHECK=0 git push",
        ):
            with self.subTest(command=command):
                self.assert_blocked(self.run_hook(command, STUB_PRECOMMIT="fail"), "pre-commit failed")
        session = self.run_hook("git push", STUB_PRECOMMIT="fail", SKIP_PRECHECK="1")
        self.assertEqual(0, session.returncode, session.stderr)

    def test_skip_precheck_falsy_values_do_not_bypass(self) -> None:
        # One truthy rule across the toolkit (shell_tokens.truthy): unset, empty,
        # 0, false, no and off (any case, padded or not) are off.
        for value in ("", "0", "false", "FALSE", "no", "No", "off", "OFF", " off ", "\tno\n"):
            with self.subTest(value=value):
                self.assert_blocked(
                    self.run_hook("git push", STUB_PRECOMMIT="fail", SKIP_PRECHECK=value), "pre-commit failed"
                )
        for value in ("1", "yes", "true", "on", "anything"):
            with self.subTest(value=value):
                result = self.run_hook("git push", STUB_PRECOMMIT="fail", SKIP_PRECHECK=value)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_the_check_runs_with_stdin_from_dev_null(self) -> None:
        # The hook's own stdin carries the tool payload; a check must not inherit
        # it (`set -m` drops the shell's implicit /dev/null for a background job).
        for variable in ("STUB_PRECOMMIT", "STUB_PYTEST"):
            with self.subTest(check=variable):
                result = self.run_hook("git push", **{variable: "stdin"})
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_warnings_reach_the_model_as_additional_context(self) -> None:
        result = self.run_hook("git push", stubs=False)
        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual("PreToolUse", output["hookSpecificOutput"]["hookEventName"])
        self.assertIn("`pre-commit` not installed", output["hookSpecificOutput"]["additionalContext"])

    def test_missing_python_allows_with_a_visible_warning(self) -> None:
        tools = tuple(tool for tool in TOOLS if tool != "python3")
        result = self.run_hook("git push", tools=tools, STUB_PRECOMMIT="fail")
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("python3 is not on PATH", context)


if __name__ == "__main__":
    unittest.main()
