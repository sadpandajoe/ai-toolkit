#!/usr/bin/env python3
"""Run a check and record the tree it ran on, for the git guard's PR gate.

Usage:
  python3 <toolkit-root>/scripts/verify.py [--partial "<what CI still runs>"] -- COMMAND [ARG ...]
  python3 <toolkit-root>/scripts/verify.py --status

Runs COMMAND in the current directory (a single argument runs through
`sh -c`), streams its output, and appends a record to `.ai-toolkit/verify.json`
at the repository's top level: the commit it started from, the exact
uncommitted content it saw, the command, its exit code and its level. Exits
with the command's exit code.

A program that could not start (exit 126 or 127, and no such program on PATH)
records nothing, so a typo blocks nothing; a check that ran and then exited 126
or 127 is a failure. A shell builtin (`cd`, `umask`, ...) checks nothing as the
whole command, so it is refused: pass a compound as one quoted argument.

Levels:
  strong   (default) the change's own failing or acceptance command passed here;
  partial  only related checks can run here; `--partial` names what CI still runs.

The git guard opens a PR (`gh pr create`) only when the newest record of every
command on that exact tree passed (rules/universal.md). Run before or after
committing: an uncommitted run counts once the commit holds exactly what was
tested. `--status` says whether HEAD has a passing record.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import verify_record  # noqa: E402
from git_guard import is_protected_path  # noqa: E402

sys.path.pop(0)

# Words a shell runs itself. As the program to run they change nothing and exit 0 (macOS
# ships /usr/bin/cd, umask, ulimit and others), which is what an unquoted
# `verify.py -- cd frontend && npm test` does.
SHELL_ONLY = {
    "cd", "pushd", "popd", "source", ".", "export", "set", "unset", "alias",
    "ulimit", "umask", "type", "hash", "read", "wait",
}
# A shell's exit codes for a command it found but could not run, or did not find.
COULD_NOT_START = {126, 127}
# What ends one shell command and starts another in a single quoted argument.
SEPARATORS = set(";&|\n")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def first_word(command: list[str]) -> str | None:
    """The program a command starts with, past any leading `NAME=value`, with `;`, `&&` and
    `(` split off (`"pytest;exit 127"`); None when a single argument does not split as
    shell words (a heredoc with an apostrophe), or starts with an operator."""
    operators = ""
    words = command
    if len(command) == 1:
        lexer = shlex.shlex(command[0], posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        operators = lexer.punctuation_chars
        try:
            words = list(lexer)
        except ValueError:
            return None
    for word in words:
        if not ASSIGNMENT.match(word):
            return None if not word or word[0] in operators else word
    return None


def could_not_start(command: list[str], exit_code: int) -> bool:
    """Whether a 126/127 exit means the program was never there, rather than a check that
    ran and failed (`"echo r > report.txt; exit 127"`). Unknown counts as ran."""
    if exit_code not in COULD_NOT_START:
        return False
    word = first_word(command)
    return word is not None and word not in SHELL_ONLY and shutil.which(word) is None


def exclude_record_directory(top: str) -> None:
    """Keep `.ai-toolkit/` out of `git status`; best effort (`.git` may be read-only)."""
    out = verify_record.git(top, "rev-parse", "--git-path", "info/exclude")
    if not out:
        return
    exclude = Path(top, out.strip())
    try:
        text = exclude.read_text() if exclude.exists() else ""
        if ".ai-toolkit/" not in text.split():
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a") as handle:
                handle.write(("" if not text or text.endswith("\n") else "\n") + ".ai-toolkit/\n")
    except OSError:
        pass


def status(top: str) -> int:
    head = verify_record.commit(top)
    if head is None:
        print("verify: no commit yet", file=sys.stderr)
        return 1
    ok, reason, record = verify_record.verdict(top, head, is_protected_path)
    if ok:
        level = record.get("level", "strong")
        extra = f"; CI still runs: {record['left_to_ci']}" if record.get("left_to_ci") else ""
        print(f"verify: HEAD has a passing record ({level}): `{record['command']}`{extra}")
        return 0
    print(f"verify: HEAD has no passing record: {reason}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="Run a check and record the tree it ran on, for the git guard's PR gate.",
    )
    parser.add_argument("--partial", metavar="WHAT_CI_RUNS", help="only related checks run here; name what CI still runs")
    parser.add_argument("--status", action="store_true", help="say whether HEAD has a passing record")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- COMMAND [ARG ...]")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command

    top = verify_record.toplevel(os.getcwd())
    if top is None:
        print("verify: not inside a git repository", file=sys.stderr)
        return 2
    if args.status:
        return status(top)
    if not command:
        parser.error("give the command to run after --")
    if args.partial is not None and not args.partial.strip():
        parser.error("--partial needs the checks CI still runs")
    lone = len(command) == 1 and not SEPARATORS & set(command[0])
    if (len(command) > 1 or lone) and first_word(command) in SHELL_ONLY:
        parser.error(
            f"`{first_word(command)}` checks nothing as a program of its own; pass a compound command as "
            'one quoted argument: verify.py -- "cd frontend && npm test"'
        )

    base = verify_record.commit(top) or verify_record.EMPTY_TREE
    known_outputs = verify_record.known_outputs(top)
    read = verify_record.worktree_changes(top, base, is_protected_path, known_outputs)
    if read is None:
        print("verify: git could not read the working tree", file=sys.stderr)
        return 2
    before, untracked = read

    shown = command[0] if len(command) == 1 else shlex.join(command)
    run = ["sh", "-c", command[0]] if len(command) == 1 else command
    try:
        exit_code = subprocess.run(run, check=False).returncode
    except OSError as error:
        print(f"verify: could not run {shown}: {error}; nothing recorded", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        exit_code = 130
    if could_not_start(command, exit_code):
        # a typo is no failed check: recording it would block the tree until that typo passes
        print(f"verify: {shown} could not start (exit {exit_code}); nothing recorded", file=sys.stderr)
        return exit_code

    after = (verify_record.worktree_changes(top, base, is_protected_path, known_outputs) or ({}, set()))[0]
    # A file the run itself created and git does not track (a cache, a report) is output,
    # not a change to the tree under test, and later runs leave it out too; an edit to
    # anything that was there is a change.
    created = set(after) - set(before)
    created_tracked = verify_record.tracked(top, created)
    # a path gone from `after` matches its base again: the run restored or reverted it
    stable = all(path in after and after[path] == blob for path, blob in before.items()) and not created_tracked
    level = "partial" if args.partial else "strong"
    record = verify_record.new_record(
        base, before, shown, exit_code, level, (args.partial or "").strip(), stable,
        untracked=untracked, created=created - created_tracked,
    )
    path = verify_record.append(top, record)
    exclude_record_directory(top)

    result = "PASS" if exit_code == 0 else f"FAIL (exit {exit_code})"
    where = base[:12] if base != verify_record.EMPTY_TREE else "an empty repository"
    pending = f" + {len(before)} uncommitted change(s)" if before else ""
    print(f"verify: {result}, {level}: `{shown}` on {where}{pending}; recorded in {path}", file=sys.stderr)
    if not stable:
        print("verify: the command changed files while it ran, so this record does not count; run it again", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
