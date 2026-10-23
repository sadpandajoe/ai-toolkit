"""The review gate: `gh pr create` needs a recorded review PASS and `--draft`.

Run as `python3 -m aitk.hooks.review_gate` with the PreToolUse payload on stdin
(`hooks/require-review-gate.sh` does this). Exit 0 allows, exit 2 blocks with
the reason on stderr, which the agent sees.

Two checks apply to every `gh pr create` (or `gh pr new`) the command runs:

- **Review.** The routing snapshot in the repository's PROJECT.md must record
  the `review` gate as PASS for the current phase, and the PASS must carry
  its evidence: the reviewer results recorded from a `bin/aitk model-run`
  envelope (`gate --gate review --result`), or a review exception (zero-logic
  or micro-fix diff, measured by `gate --exception`, rules/gates.md) backed by
  this phase's passing verification run. A PASS typed without either does not
  count. This is the `gate_blockers` check `bin/aitk deliver` applies, so the
  hook and deliver cannot disagree. A missing, unreadable or malformed
  PROJECT.md or snapshot, and a missing gate, block. `SKIP_PR_GATE=1` (set in
  the environment the session started with; a command that assigns one itself
  is blocked by the git guard) is the user's override for work outside a
  workflow and lifts this check only.
- **Draft.** The PR must be opened with `--draft`. `AITK_PR_READY=1` (set in the
  environment the session started with, only when the user asked for a ready PR
  in words; a command that assigns one itself is blocked by the git guard)
  lifts this check only. `bin/aitk deliver` always opens a draft and has no
  ready flag, so the hook has nothing to check there.

A command that cannot be parsed, nests deeper than the tokenizer follows, passes
its work budget (rescan tails and `$(...)` or backtick bodies are charged to it) or
hands git text that mentions a gated operation counts as a PR creation that is NOT
a draft, whatever its text says (a pattern over the text accepts a first `-d` and
misses a later `-d=false`). The last two are `unreadable`: no directory is known
for them, the review check does not run on the starting repository's record, and
the reason says the command could not be read in full (not that it changes
directory). Git's own payloads are not walked (block on sight): a segment that
carries an inline alias (`-c alias.*`, `--config-env=alias.*`, `GIT_CONFIG_KEY_n=alias.*`),
or the words after `git rebase -x`/`--exec`, `git bisect run` and `git submodule
foreach`, or the git command after `git for-each-repo`'s options, that mention `gh`
followed by `pr`, a push or `pr create`, make the command unreadable; without such a mention they are ordinary commands. Every other
PR creation in one request is checked against the repository it runs in (`cd`,
`pushd` and `env -C` are followed). The wrapper's text prefilter only hands this
module a command that mentions `gh`..`create`/`new` (any case: `GH`) or `deliver`, so it
is the prefilter that decides what reaches the tokenizer (see the limits below). An error
inside this module blocks with the error. So does running out of time: a PreToolUse hook
past its `timeout` (10 s) fails open, so `main()` parses under `DEADLINE_SECONDS` and a
command not read in time blocks. `cd "$(git rev-parse --show-toplevel)"` (exactly that
text, unquoted or in backticks too) follows the git top level of the directory it runs
in; any other `$`, a glob character or a tab in a `cd` target is "cannot follow".

Known limits (this is a tripwire against skipping the workflow, not a shell
sandbox):
  - The hook checks that the review PASS carries a record, not that the
    recorded tree is the one the PR opens from; `bin/aitk deliver` compares
    the trees, a direct `gh pr create` does not.
  - Command matching is static: `cd` inside a conditional or subshell is
    treated as taken, and `gh api` or an alias can open a PR unseen.
  - `gh` is not `git`: `GIT_DIR=/x/.git gh pr create --draft --fill` (or
    `GIT_WORK_TREE`) is checked against the working directory, not `/x`, so the
    working directory's recorded review vouches for it (pinned in
    tests/test_pr_gate_hook.py).
  - The prefilter is a text match: a command that hides `gh` or `create` behind
    quotes (`g'h' pr create --fill`) and does not mention `deliver` is never
    handed to this module, so it is not checked (pinned by `PREFILTER_LIMITS`
    in tests/test_pr_gate_hook.py).
  - Over-blocks, accepted: any `gh pr` or push mention next to an inline alias or
    in the words git runs blocks (`git -c alias.x=y commit -m 'gh pr create docs'`);
    config values and tool options other than aliases that make git run a shell
    (`core.pager`, `credential.helper`, `difftool -x`, `sequence.editor`) and
    `GIT_CONFIG_*` exported by an earlier command are not seen.
  - A wrapper this module does not know makes the same creation visible in two
    directory contexts (`flock /tmp/lock env -C /reviewed gh pr create --draft
    --fill` is also read as a plain `gh pr create` in the starting directory), so
    it blocks from a directory without a recorded review: an accepted over-block.
  - PROJECT.md is looked up from the working directory to the git top level,
    so a linked worktree does not see the main checkout's PROJECT.md and a PR
    opened from one is blocked until its own workflow records the gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from aitk.hooks.shell_tokens import Command, DeadlineExceeded, commands, deadline, positional, truthy


# The in-process time limit of `main()`: a hook past its timeout in hooks/hooks.json (10 s)
# fails open, so the gate stops itself first and blocks.
DEADLINE_SECONDS = 6.0
GH_GLOBAL_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
# gh pr create flags that take a value, so the draft scan skips their values.
CREATE_VALUE_FLAGS = {
    "-a", "--assignee", "-B", "--base", "-b", "--body", "-F", "--body-file",
    "-H", "--head", "-l", "--label", "-m", "--milestone", "-p", "--project",
    "-r", "--reviewer", "-T", "--template", "-t", "--title", "-R", "--repo",
    "--hostname",
}
CREATE_SHORT_VALUE = {"a", "B", "b", "F", "H", "l", "m", "p", "r", "T", "t", "R"}
DRAFT_TRUE = {"true", "1", "t"}


def gh_creates_pr(args: list[str]) -> bool:
    if {"-h", "--help"} & set(args):
        return False
    return positional(args, GH_GLOBAL_VALUE_FLAGS)[:2] in (["pr", "create"], ["pr", "new"])


def is_draft(args: list[str]) -> bool:
    """Whether a `gh pr create` argument list asks for a draft PR."""
    draft = False
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            break
        if arg in CREATE_VALUE_FLAGS:
            skip = True
        elif arg == "--draft":
            draft = True
        elif arg.startswith("--draft="):
            draft = arg.split("=", 1)[1].strip().lower() in DRAFT_TRUE
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            for position, char in enumerate(arg[1:], 1):
                if char == "d":
                    # pflag reads `-d=false` as the bool flag set to false and keeps
                    # reading a cluster without `=`, so `-dd=false` ends not draft
                    value = arg[position + 1 :]
                    if value[:1] == "=":
                        draft = value[1:].strip().lower() in DRAFT_TRUE
                        break
                    draft = True
                if char in CREATE_SHORT_VALUE:
                    break
    return draft


class Creation:
    """One PR creation found in the command."""

    def __init__(self, command: Command, draft: bool) -> None:
        self.workdir = command.workdir
        self.draft = draft
        self.unresolved = command.unresolved
        self.unreadable = command.unreadable


def pr_creations(text: str, cwd: str) -> list[Creation]:
    found: list[Creation] = []
    for command in commands(text, cwd):
        if command.unresolved:
            # Unreadable: count it as a creation, never as a draft.
            found.append(Creation(command, False))
        elif command.is_gh and gh_creates_pr(command.argv[1:]):
            found.append(Creation(command, is_draft(command.argv[1:])))
    return found


class Blocked(Exception):
    pass


REVIEW_HELP = (
    "Run the workflow that owns this change (create-feature or fix-bug), or "
    "`review-code` on the branch for a change outside any workflow, so the "
    "review gate is recorded by the workflow; then retry. The user asking "
    "for the PR already authorizes that review. Do not bypass this on your "
    "own: if review-code cannot run, stop and ask the user, who alone can "
    "override it."
)


def review_block(reason: str) -> Blocked:
    return Blocked(
        "BLOCKED: `gh pr create` needs a recorded review gate (rules/gates.md), "
        f"and {reason}.\n" + REVIEW_HELP
    )


def draft_block(unresolved: bool = False) -> Blocked:
    unreadable = (
        " This command could not be read in full (an unbalanced quote, nesting past "
        "the hook's depth, more text than it will walk, or text handed to git that mentions "
        "`gh pr`: an inline alias, `rebase -x`, `bisect run`, `submodule foreach`, "
        "`for-each-repo`), so it "
        "cannot show a draft: "
        "run `gh pr create --draft` as a plain command of its own."
        if unresolved
        else ""
    )
    return Blocked(
        "BLOCKED: pull requests open as drafts (rules/universal.md). Add `--draft` "
        f"to `gh pr create`.{unreadable} A ready PR "
        "needs the user's explicit request in words; do not bypass this on your "
        "own: if the user wants a ready PR, stop and ask the user, who alone can "
        "override it."
    )


def git_toplevel(path: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def find_project_file(start: str, stop: str) -> str | None:
    """Nearest PROJECT.md from the working directory up to the repo root."""
    current = os.path.realpath(start)
    stop = os.path.realpath(stop)
    while True:
        candidate = os.path.join(current, "PROJECT.md")
        if os.path.isfile(candidate):
            return candidate
        if current == stop or os.path.dirname(current) == current:
            return None
        current = os.path.dirname(current)


def check_review(workdir: str | None, unreadable: bool = False) -> None:
    from aitk.project_state import gate_blockers, parse_project_state

    if unreadable:
        raise review_block(
            "the command could not be read in full (more text than the hook will walk, or "
            "text handed to git that mentions `gh pr`), so what it runs and the repository it "
            "opens the PR in are unknown (run `gh pr create` as its own simple command)"
        )
    if workdir is None:
        raise review_block(
            "the command changes directory in a way this hook cannot follow, so the "
            "repository it opens the PR in is unknown (run `gh pr create` as its own "
            "simple command)"
        )
    root = git_toplevel(workdir)
    if root is None:
        return
    project_file = find_project_file(workdir, root)
    if project_file is None:
        raise review_block("no PROJECT.md exists in the repository, so no workflow ran")
    try:
        with open(project_file, encoding="utf-8") as handle:
            content = handle.read()
    except OSError as error:
        raise review_block(f"PROJECT.md could not be read ({error.strerror or error})")
    try:
        snapshot = parse_project_state(content)
    except Exception as error:  # noqa: BLE001 - any parse failure blocks
        raise review_block(f"the routing snapshot in PROJECT.md is unreadable ({error})")
    if snapshot is None:
        raise review_block("PROJECT.md has no routing snapshot, so no workflow classified this change")
    try:
        blockers = gate_blockers(snapshot, ["review"])
    except Exception as error:  # noqa: BLE001
        raise review_block(f"the review gate record in PROJECT.md is unreadable ({error})")
    if blockers:
        raise review_block("the snapshot does not show it passing: " + "; ".join(blockers))


def evaluate(command: str, cwd: str, environ: dict[str, str]) -> None:
    """Raise Blocked when any PR creation in `command` fails a check."""
    session_skip = truthy(environ.get("SKIP_PR_GATE"))
    session_ready = truthy(environ.get("AITK_PR_READY"))
    checked: list[str | None] = []
    for creation in pr_creations(command, cwd):
        # Review first, so an unreviewed change is sent to review before the
        # draft question comes up; each override lifts only its own check.
        if not session_skip and (creation.unreadable or creation.workdir not in checked):
            checked.append(creation.workdir)
            check_review(creation.workdir, creation.unreadable)
        if not creation.draft and not session_ready:
            raise draft_block(creation.unresolved)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or ""
        cwd = payload.get("cwd") or ""
        if not isinstance(command, str) or not isinstance(cwd, str):
            return 0
        if not command or not cwd or not os.path.isdir(cwd):
            return 0
        with deadline(DEADLINE_SECONDS):
            evaluate(command, cwd, dict(os.environ))
    except Blocked as blocked:
        print(str(blocked), file=sys.stderr)
        return 2
    except DeadlineExceeded:
        # A hook past its timeout fails open. The wrapper's prefilter already selected
        # this command as a possible PR creation, so one not read in time blocks.
        print(
            "BLOCKED: this command is too large or complex for the review gate to check in "
            "time, so it cannot show that it is a reviewed draft PR. Run `gh pr create "
            "--draft` as a simpler command of its own; do not work around the hook.",
            file=sys.stderr,
        )
        return 2
    except Exception as error:  # noqa: BLE001 - an internal error blocks
        print(
            f"BLOCKED: the review gate hook failed ({type(error).__name__}: {error}). "
            "Stop and ask the user; do not work around the hook.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
