"""The review gate: `gh pr create` needs a recorded review PASS and `--draft`.

Run as `python3 -m aitk.hooks.review_gate` with the PreToolUse payload on stdin
(`hooks/require-review-gate.sh` does this). Exit 0 allows, exit 2 blocks with
the reason on stderr, which the agent sees.

Two checks apply to every `gh pr create` (or `gh pr new`) the command runs:

- **Review.** The routing snapshot in the repository's PROJECT.md must record
  the `review` gate as PASS for the current phase, and the PASS must carry
  its evidence: the reviewer results recorded from a `bin/aitk model-run`
  envelope (`gate --gate review --result`), or a review exception (zero-logic
  or micro-fix diff, rules/gates.md) backed by this phase's passing
  verification run. A PASS typed without either does not count. This is the
  `gate_blockers` check `bin/aitk deliver` applies, so the hook and deliver
  cannot disagree. A `published_pr` checkpoint reservation no longer stands
  in for a review: deliver opens the PR in the phase whose review it read. A
  missing, unreadable or malformed PROJECT.md or snapshot, and a missing
  gate, block. `SKIP_PR_GATE=1` (a command prefix or the session env) is the
  user's override for work outside a workflow and lifts this check only.
- **Draft.** The PR must be opened with `--draft`. `AITK_PR_READY=1` (a command
  prefix or the session env, set only when the user asked for a ready PR in
  words) lifts this check only. `bin/aitk deliver ... --ready` counts as
  `gh pr create` without `--draft`: the hook never sees the `gh` call deliver
  makes.

A command that cannot be parsed, or nests deeper than the tokenizer follows,
counts as a PR creation (the wrapper's prefilter already saw `gh` and
`create`), and every PR creation in one request is checked against the
repository it runs in. An error inside this module blocks with the error.

Known limits (this is a tripwire against skipping the workflow, not a shell
sandbox):
  - The hook checks that the review PASS carries a record, not that the
    recorded tree is the one the PR opens from; `bin/aitk deliver` compares
    the trees, a direct `gh pr create` does not.
  - Command matching is static: `cd` inside a conditional or subshell is
    treated as taken, and `gh api` or an alias can open a PR unseen.
  - PROJECT.md is looked up from the working directory to the git top level,
    so a linked worktree does not see the main checkout's PROJECT.md and a PR
    opened from one is blocked until its own workflow records the gate.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from aitk.hooks.shell_tokens import Command, commands, positional, truthy


GH_GLOBAL_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
# gh pr create flags that take a value, so the draft scan skips their values.
CREATE_VALUE_FLAGS = {
    "-a", "--assignee", "-B", "--base", "-b", "--body", "-F", "--body-file",
    "-H", "--head", "-l", "--label", "-m", "--milestone", "-p", "--project",
    "-r", "--reviewer", "-T", "--template", "-t", "--title", "-R", "--repo",
    "--hostname",
}
CREATE_SHORT_VALUE = {"a", "B", "b", "F", "H", "l", "m", "p", "r", "T", "t", "R"}


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
            draft = arg.split("=", 1)[1].strip().lower() in {"true", "1", "t"}
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            for char in arg[1:]:
                if char == "d":
                    draft = True
                if char in CREATE_SHORT_VALUE:
                    break
    return draft


def is_ready_delivery(command: Command) -> bool:
    """`bin/aitk deliver ... --ready` opens a non-draft PR through aitk."""
    argv = command.argv
    if not argv:
        return False
    if command.name in {"python", "python3"} and argv[1:3] == ["-m", "aitk.cli"]:
        argv = ["aitk", *argv[3:]]
    if os.path.basename(argv[0]) != "aitk":
        return False
    rest = positional(argv[1:], {"--root"})
    return rest[:1] == ["deliver"] and "--ready" in argv


DRAFT_FLAG = re.compile(r"(?<![\w-])(?:--draft(?:=(?:true|1|t))?|-[A-Za-z]*d[A-Za-z]*)(?![\w=-])")


class Creation:
    """One PR creation found in the command."""

    def __init__(self, command: Command, draft: bool) -> None:
        self.workdir = command.workdir
        self.draft = draft
        self.review_skipped = truthy(command.assignments.get("SKIP_PR_GATE"))
        self.ready_allowed = truthy(command.assignments.get("AITK_PR_READY"))


def pr_creations(text: str, cwd: str) -> list[Creation]:
    found: list[Creation] = []
    for command in commands(text, cwd):
        if command.unresolved:
            # Unparseable: count it as a creation; trust `--draft` only when the
            # raw text carries it.
            found.append(Creation(command, bool(DRAFT_FLAG.search(command.text))))
        elif command.name == "gh" and gh_creates_pr(command.argv[1:]):
            found.append(Creation(command, is_draft(command.argv[1:])))
        elif is_ready_delivery(command):
            found.append(Creation(command, False))
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


def draft_block() -> Blocked:
    return Blocked(
        "BLOCKED: pull requests open as drafts (rules/universal.md). Add `--draft` "
        "to `gh pr create`, or drop `--ready` from `bin/aitk deliver`. A ready PR "
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


def check_review(workdir: str | None) -> None:
    from aitk.project_state import gate_blockers, parse_project_state

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
        if not (session_skip or creation.review_skipped) and creation.workdir not in checked:
            checked.append(creation.workdir)
            check_review(creation.workdir)
        if not creation.draft and not (session_ready or creation.ready_allowed):
            raise draft_block()


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
        evaluate(command, cwd, dict(os.environ))
    except Blocked as blocked:
        print(str(blocked), file=sys.stderr)
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
