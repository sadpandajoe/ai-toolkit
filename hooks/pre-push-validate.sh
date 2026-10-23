#!/bin/bash
#
# pre-push-validate.sh — provider-neutral PreToolUse hook
#
# Runs lint + targeted tests on the commits that are about to be pushed,
# using the repo's pinned tool versions (not the system's). Blocks the push
# on a failure; a check that runs out of time warns and the push proceeds.
#
# Tiers:
#   1. pre-commit on all changed files (preferred — runs the repo's full
#      pinned hook set: ruff, mypy, prettier, oxlint, eslint, tsc, etc.).
#      Fallback for repos without .pre-commit-config.yaml or `pre-commit`:
#      ruff on changed *.py files via repo venv > uv run > skip.
#   2. pytest on changed test files via the repo's venv.
#
# Time budgets: the command parse 15 s (an in-process SIGALRM deadline: a parse
# that runs out of time reads as an unreadable command and blocks, because a hook
# past its timeout fails open), lint 180 s, tests 90 s, each check with a 5 s grace
# before KILL, so all of them together stay under the 300 s hook timeout in
# hooks/hooks.json (15 + 180 + 90 + 2 x 5 = 295). A
# hook the runtime kills at its own timeout lets the push through; a check
# that runs out of its budget here warns and the push proceeds. A shell
# watchdog enforces every budget on the check's whole process group. Bash
# reports a signal death and an explicit `exit 143` with the same status, so a
# small launcher (python3, isolated mode) runs the check as its child, survives
# the watchdog's TERM and records how the check really ended (written to a
# temporary file and renamed, so a record is whole or absent). Only an overdue
# check (deadline marker present) that the watchdog's own TERM or KILL killed
# (signal 15 or 9), that ended 0 after the TERM, or that left no record while
# the launcher itself died from the watchdog's TERM or KILL (status 143 or 137)
# is a budget warning. One that exits non-zero on its own, even 137 or 143 or
# during the grace, one that dies from any other signal (SIGABRT, SIGSEGV, ...),
# one that dies early (SIGKILL, its own exit 124), one that takes the launcher
# down with a different signal (`kill -USR1 0`: no record, another status), and
# a record that is not `exit N` or `signal N` or that disagrees with a clean
# launcher exit, is a failure and blocks. A launcher that cannot write its
# record exits with a sentinel (253) that blocks too. pre-commit runs
# its remaining hooks after one fails, so an overdue pre-commit whose output
# already shows a failed hook (`....Failed`) blocks as well.
# AITK_PRECHECK_LINT_BUDGET and AITK_PRECHECK_TEST_BUDGET can only lower the
# budgets.
#
# Accepted limits, each on the safe or the visible side:
#   - A wrapper that turns the watchdog's TERM into an exit status (a launcher
#     that exits 143 after its child died, `uv run` fallbacks) looks like a check
#     that failed on its own, so it blocks instead of warning, with a reason that
#     says the check failed rather than ran out of time.
#   - A check that sends KILL to its own process group after the deadline takes
#     the launcher down with the signal the watchdog would use, so it reads as a
#     killed check and warns.
#   - Failure detection past the budget exists only for pre-commit output. A
#     pytest run (`-x`) that already failed a test and then overruns TEST_BUDGET
#     in a slow fixture finalizer ends by the watchdog's TERM and warns; the
#     failure is not detected.
#
# Known limit: cleanup ends the check's own process group. A check that enables
# its own job control (`set -m`) or starts a descendant in a new session or
# group (`setsid`, `nohup setsid`, a daemonizing tool) puts that descendant in
# another group, so the hook neither signals it nor waits for it; it can
# outlive the hook. A static tripwire, not a process sandbox.
#
# Bypass is the user's alone: SKIP_PRECHECK in the environment Claude Code or
# Codex started with, set to anything but unset, empty, 0, false, no or off
# (any case; the same rule as aitk/hooks/shell_tokens.py `truthy`). A prefix on
# the push itself does not count (the git guard blocks it). The block message
# never suggests it.
#
# Which repository: the push is checked in the directory the shared tokenizer
# says it runs in (`git -C` is followed lexically with os.path.normpath: no
# symlink resolution, no `~` expansion, at most 16 hops). A push whose
# repository it cannot tell (--git-dir, --work-tree, GIT_DIR or GIT_WORK_TREE,
# more than 16 `-C` hops, or a directory that does not exist, which is what
# `git -C ~/x push` and `git -C $DIR push` name when the text is read literally;
# a `-C` word with a `$`, `~`, backtick, glob character (`*?[`), tab or newline, or a
# `cd` word with a `$`, backtick, glob character, tab or newline, is unknown whether or
# not a directory of that literal name exists: `-C "$X/.."` is not the folder above one
# named `$X`, and `-C '/p/[w]ork'` is a pattern; the one `$` read on purpose is
# `cd "$(git rev-parse --show-toplevel)"` (that exact text, unquoted or in backticks
# too), which is the git top level of the directory it runs in;
# a dashed `git-push` is a push too, and any other `git-*` word is an ordinary
# executable) blocks with "cannot tell which repository this push
# runs in; run it directly" instead of validating the caller's repository. So
# does an unreadable command that mentions a push: the tokenizer never resolves
# what git itself runs, so a segment with an inline alias (`-c alias.*`,
# `--config-env=alias.*`, GIT_CONFIG_KEY_n=alias.*), the words after `git rebase
# -x`, `git bisect run`, `git submodule foreach` or the git command after `git
# for-each-repo`'s options, or a command past the work
# budget is unreadable when it mentions `push` (the same message, with "could not
# be read in full"); an unreadable command without a push mention does not block.
# Only the user's SKIP_PRECHECK lifts it. Accepted limits: git reached through a variable
# (`G=git-push; $G origin main`) is not resolved here and is not seen (the git guard
# does read it); any `push` word in
# such text blocks (`./push.sh`, `echo push`, `git config --get alias.push`, `git grep
# alias.x=1 push`, `git --exec-path push`), any later argument that names a git entry point
# restarts the scan and reads as that command (`chmod +x bin/git-push`, `make git-push`,
# `./git-push` an executable of that name; after an unknown wrapper it cannot be told from
# a command, so `setsid git-push` is still seen), and a symlink in a `-C` path is
# not resolved, so `git -C link/.. push` may validate (or skip) the wrong
# repository; shell-running config values other than aliases (`core.pager`,
# `credential.helper`, ...) and GIT_CONFIG_* exported by an earlier command are
# not seen.
#
# Output:
#   exit 2 — block; the reason (and the tools' output) on stderr.
#   exit 0 — allow; warnings go to stdout as hookSpecificOutput.additionalContext,
#            which the model sees.
# Setup problems (no python3, git, repo or base commit) allow the push.

set -u

INPUT=$(cat)

# Fast exit: most Bash calls are not pushes. The word is matched the way the parser
# reads it: quoting and a backslash-newline are removed first (`pu'sh'`, `pu\<LF>sh`),
# so the input here (JSON: `\\` `\n` `\"`) may hold quote, backslash or `n` characters
# between the letters. Extra matches only cost the parser a run.
PUSH_WORD="p[\\\"'\`n]*u[\\\"'\`n]*s[\\\"'\`n]*h"
[[ $INPUT == *push* || $INPUT =~ $PUSH_WORD ]] || exit 0

emit_context() {
    # One JSON object on stdout: model-visible context for an allowed push.
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json, sys; print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": sys.argv[1]}}))' "$1"
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "pre-push validation did not run: python3 is not on PATH. Run the repository lint and tests before relying on this push."}}'
    exit 0
fi
command -v git >/dev/null 2>&1 || exit 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Find the push: the shared tokenizer yields every command the shell would run.
# Output: "push<TAB>workdir" for the first push, "unknown<TAB>" when any push's
# repository is unknown, "unreadable<TAB>" when a command that mentions a push
# could not be read, nothing otherwise.
read -r -d '' PARSER <<'PY'
import json, os, sys
from aitk.hooks import shell_tokens

# In-process time limit: this hook fails open past its 300 s timeout, so the parse stops
# itself, with the lint and test budgets and their grace periods below it (see the header).
DEADLINE = 15.0

try:
    payload = json.loads(sys.stdin.read() or "{}")
except ValueError:
    raise SystemExit(0)
command = (payload.get("tool_input") or {}).get("command") or ""
cwd = payload.get("cwd") or ""
if not (isinstance(command, str) and isinstance(cwd, str) and command and os.path.isdir(cwd)):
    raise SystemExit(0)


def parse():
    pushes = []
    unreadable = False
    for found in shell_tokens.commands(command, cwd):
        if found.unreadable:
            # its text cannot show what runs: only one that mentions a push can be one
            unreadable = unreadable or shell_tokens.mentions_push(found.text)
            continue
        if found.unresolved:
            if shell_tokens.words_in_order(found.text, shell_tokens.WORD_GIT, shell_tokens.WORD_PUSH):
                pushes.append(found.workdir)
            continue
        argv = shell_tokens.git_argv(found.argv)  # `git-push origin x` reads as `git push origin x`
        if argv is None:
            continue
        args = argv[1:]
        workdir, index = shell_tokens.git_globals(args, found.workdir, found.assignments)
        if args[index:index + 1] == ["push"]:
            pushes.append(workdir)
    # A push whose repository is unknown (None) or whose command could not be read is
    # never run against the caller's: the first field says so and the shell blocks
    # after the bypass check.
    if unreadable:
        return "unreadable\t"
    if pushes:
        # a directory that does not exist is unknown too: `-C ~/x` and `-C $DIR` are read
        # literally here (no expansion), so they name nothing. A `-C` or `cd` word the shell
        # expands ($, ~, a backtick), a glob (*?[) or one that holds a newline or a tab is
        # already None (git_globals, advance_dir); a newline or tab in the path is refused
        # here too, since the shell below reads it back one line at a time with `read`,
        # which strips a trailing tab
        unknown = any(
            workdir is None or "\n" in workdir or "\t" in workdir or not os.path.isdir(workdir)
            for workdir in pushes
        )
        return "unknown\t" if unknown else f"push\t{pushes[0]}"
    return None


try:
    with shell_tokens.deadline(DEADLINE):
        line = parse()
except shell_tokens.DeadlineExceeded:
    line = "unreadable\t"  # too large or complex to read in time: blocks unless the user skips
if line:
    print(line)
PY

PARSED=$(printf '%s' "$INPUT" | (cd "$ROOT" && PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c "$PARSER")) || exit 0
[[ $PARSED == push$'\t'* || $PARSED == unknown$'\t'* || $PARSED == unreadable$'\t'* ]] || exit 0
IFS=$'\t' read -r KIND CWD <<<"$PARSED"

# Bypass: the user's session env only. Same truthy rule as the toolkit's other
# hooks (aitk.hooks.shell_tokens.truthy): unset, empty, 0, false, no and off in
# any case, padded or not, are off; anything else is on.
SKIP_VALUE=${SKIP_PRECHECK:-}
SKIP_VALUE=${SKIP_VALUE#"${SKIP_VALUE%%[![:space:]]*}"}
SKIP_VALUE=${SKIP_VALUE%"${SKIP_VALUE##*[![:space:]]}"}
case "$SKIP_VALUE" in
    "" | 0 | [Ff][Aa][Ll][Ss][Ee] | [Nn][Oo] | [Oo][Ff][Ff]) ;;
    *) exit 0 ;;
esac

# A push whose repository the parser could not tell (--git-dir, --work-tree,
# GIT_DIR, GIT_WORK_TREE, too many -C hops), or a command it could not read that
# mentions a push, is not checked against the caller's repository: that would
# validate the wrong one.
if [[ $KIND == unknown || $KIND == unreadable ]]; then
    if [[ $KIND == unreadable ]]; then
        WHY="this command could not be read in full and mentions a push, so pre-push validation cannot tell which repository this push runs in; run it directly."
    else
        WHY="pre-push validation cannot run: cannot tell which repository this push runs in; run it directly."
    fi
    {
        echo ""
        echo "BLOCKED: $WHY"
        echo ""
        echo "Run the push as a plain command of its own in the repository (no --git-dir or --work-tree, no inline git alias, rebase -x, bisect run, submodule foreach or for-each-repo text that mentions a push, nothing too large to read quickly). If it cannot be run directly, stop and ask the user; only the user can skip this check."
    } >&2
    exit 2
fi
[[ -d "$CWD" ]] || exit 0

# Must be inside a git repo
REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0

# Determine which commits will be pushed.
# Prefer upstream tracking; otherwise compare against origin/main or main.
UPSTREAM=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
if [[ -n "$UPSTREAM" ]]; then
    RANGE="$UPSTREAM..HEAD"
else
    BASE=""
    for ref in origin/main origin/master main master; do
        BASE=$(git -C "$REPO_ROOT" merge-base HEAD "$ref" 2>/dev/null) && break || BASE=""
    done
    [[ -z "$BASE" ]] && exit 0
    RANGE="$BASE..HEAD"
fi

# Changed files (added/copied/modified/renamed), still present on disk
CHANGED_FILES=()
while IFS= read -r f; do
    [[ -n "$f" && -f "$REPO_ROOT/$f" ]] && CHANGED_FILES+=("$f")
done < <(git -C "$REPO_ROOT" diff --name-only --diff-filter=ACMR "$RANGE" 2>/dev/null)

[[ ${#CHANGED_FILES[@]} -eq 0 ]] && exit 0

PY_FILES=()
TEST_FILES=()
for f in "${CHANGED_FILES[@]}"; do
    [[ $f == *.py ]] || continue
    PY_FILES+=("$f")
    if [[ $f =~ (^|/)test_[^/]+\.py$ || $f =~ (^|/)tests?/.*\.py$ || $f =~ _test\.py$ ]]; then
        TEST_FILES+=("$f")
    fi
done

budget() {
    # The default, or a lower override; never higher.
    local default=$1 override=$2
    if [[ $override =~ ^[0-9]+$ ]] && (( override > 0 && override < default )); then
        echo "$override"
    else
        echo "$default"
    fi
}
LINT_BUDGET=$(budget 180 "${AITK_PRECHECK_LINT_BUDGET:-}")
TEST_BUDGET=$(budget 90 "${AITK_PRECHECK_TEST_BUDGET:-}")
GRACE=5

# Wait up to GRACE seconds for process group $1 to empty, then KILL what is left.
end_group() {
    local group=$1 waited=0
    while (( waited < GRACE * 5 )); do
        kill -0 -- "-$group" 2>/dev/null || return 0
        sleep 0.2
        waited=$((waited + 1))
    done
    kill -KILL -- "-$group" 2>/dev/null
}

# Runs the check as a child and records how it ended in the file named by $1, as
# `exit N` or `signal N`. It survives the watchdog's TERM (a handler, which the
# child resets to default on exec); a KILL takes it down before it writes, so a
# missing record means the watchdog killed the check. The record is written to
# `$1.tmp` and renamed, so it is never half written. If it cannot be written the
# launcher exits 253 (RECORD_FAILED in with_budget), which blocks: with no record
# an overdue check that failed on its own would be read as a killed one.
read -r -d '' LAUNCHER <<'PY'
import os, signal, subprocess, sys

status, argv = sys.argv[1], sys.argv[2:]
signal.signal(signal.SIGTERM, lambda *_: None)
try:
    code = subprocess.Popen(argv).wait()
except OSError as error:
    print(f"{argv[0]}: {error.strerror}", file=sys.stderr)
    code = 127
how = "signal" if code < 0 else "exit"
try:
    with open(status + ".tmp", "w") as handle:
        handle.write(f"{how} {abs(code)}\n")
    os.replace(status + ".tmp", status)
except OSError as error:
    print(f"pre-push: could not record how the check ended ({error.strerror})", file=sys.stderr)
    raise SystemExit(253)
raise SystemExit(128 - code if code < 0 else code)
PY

CHECK_OUTPUT=""
RECORD_FAILED=253 # the launcher's exit when it could not write its status record

# Run "$@" with stdin from /dev/null and a SECONDS deadline in its own process
# group, its output captured (replayed on stderr when it ends, and left in
# CHECK_OUTPUT). Always end the group after the check exits (TERM, then KILL
# after GRACE), including descendants left by an early pass or failure. Return
# 124 only for an overdue check (watchdog marker) that the watchdog's TERM or
# KILL killed (signal 15 or 9), that exited 0 after the TERM, or that left no
# record while the launcher died from the watchdog's TERM or KILL (137 or 143);
# any other end stays a failure, even a check's own 137 or 143, another signal, a
# missing record under any other status, a malformed record or RECORD_FAILED. Return
# 125 for deadline marker setup failure, distinct from a failed check. A check's
# own exit 124 or 125 is mapped to failure status 1.
with_budget() {
    local seconds=$1
    shift
    CHECK_OUTPUT=""
    local marker
    marker=$(mktemp "${TMPDIR:-/tmp}/aitk-prepush.XXXXXX") || return 125
    rm -f "$marker" || return 125
    [[ ! -e $marker ]] || return 125
    local status="$marker.status" output="$marker.output"
    set -m # own process group: the pid is the group id
    python3 -I -c "$LAUNCHER" "$status" "$@" </dev/null >"$output" 2>&1 &
    local pid=$!
    set +m
    (
        sleeper=""
        trap '[[ -n "$sleeper" ]] && kill "$sleeper" 2>/dev/null; exit 0' TERM
        sleep "$seconds" &
        sleeper=$!
        wait "$sleeper"
        if kill -0 "$pid" 2>/dev/null; then
            : >"$marker"
            kill -TERM -- "-$pid" 2>/dev/null
            kill -TERM "$pid" 2>/dev/null
            end_group "$pid"
            kill -KILL "$pid" 2>/dev/null
        fi
    ) &
    local watchdog=$!
    wait "$pid" 2>/dev/null
    local rc=$?
    kill -TERM "$watchdog" 2>/dev/null
    wait "$watchdog" 2>/dev/null
    # Even an early pass or failure can leave a descendant holding output open.
    kill -TERM -- "-$pid" 2>/dev/null
    end_group "$pid"
    local ended=""
    [[ -f $status ]] && ended=$(<"$status")
    if [[ -f $output ]]; then
        CHECK_OUTPUT=$(<"$output")
        cat "$output" >&2
    fi
    local overdue=0
    [[ -e $marker ]] && overdue=1
    rm -f "$marker" "$status" "$status.tmp" "$output"
    # A record is exactly `exit N` or `signal N`; anything else is corrupt.
    local record='^(exit|signal) [0-9]+$'
    if [[ -n $ended && ! $ended =~ $record ]]; then
        return 1
    fi
    if [[ $overdue -eq 1 && $rc -ne $RECORD_FAILED ]]; then
        case "$ended" in
            # exit 0 after the TERM, or the watchdog's own TERM or KILL
            "exit 0" | "signal 15" | "signal 9") return 124 ;;
            # no record: only the launcher's death from the watchdog's TERM or KILL
            "") [[ $rc -eq 137 || $rc -eq 143 ]] && return 124 ;;
        esac
    fi
    # A launcher that exits 0 has written `exit 0`; without it the record is lost.
    if [[ $rc -eq 0 && $ended != "exit 0" ]]; then
        return 1
    fi
    [[ $rc -eq 124 || $rc -eq 125 ]] && rc=1
    return $rc
}

FAILURES=""
WARNINGS=""

# ── Tier 1: lint/format/type-check via the repo's pinned hooks ──────────────
#
# Returns:
#   0   — ran and passed (or nothing to do)
#   1   — ran and failed (block the push)
#   124 — watchdog confirmed the deadline expired (warn)
#   125 — deadline marker setup failed (block with a setup reason)
#   99  — not configured here, caller should try the fallback path
run_precommit() {
    cd "$REPO_ROOT" || return 99
    [[ -f .pre-commit-config.yaml ]] || return 99
    # Hooks must see the repo's own toolchain: pre-commit puts the bin dir of
    # the Python it runs under first on PATH, so a pyenv-level `pre-commit`
    # shadows the repo venv's pylint/mypy with another interpreter. Prefer the
    # repo venv's bin dir when it holds its own pre-commit.
    local venv_bin=""
    for venv_bin in "$REPO_ROOT/.venv/bin" "$REPO_ROOT/venv/bin"; do
        [[ -x "$venv_bin/pre-commit" ]] && break
        venv_bin=""
    done
    if [[ -z $venv_bin ]] && ! command -v pre-commit >/dev/null 2>&1; then
        WARNINGS+=$'\n  - pre-commit config present but `pre-commit` not installed; install it so push-time lint matches CI.'
        return 99
    fi
    [[ -n $venv_bin ]] && local -x PATH="$venv_bin:$PATH"
    # Base-relative hooks (pylint) diff against the branch being pushed to
    # rather than master, so a release branch is not linted for its whole
    # divergence from master. A caller's GITHUB_BASE_REF wins. The tracked
    # branch comes from git's config, not from UPSTREAM, whose remote and
    # branch names may both contain slashes.
    if [[ -z ${GITHUB_BASE_REF:-} && -n $UPSTREAM ]]; then
        local branch merge
        branch=$(git symbolic-ref -q --short HEAD) &&
            merge=$(git config --get "branch.$branch.merge") &&
            local -x GITHUB_BASE_REF="${merge#refs/heads/}"
    fi
    # `--files` makes pre-commit operate on these files regardless of stage
    # gating. Each hook's own `files:` regex filters down further, so hooks
    # that don't match the changed set no-op. Exit 1 covers both "hook
    # failed" and "hook modified files"; both block the push.
    with_budget "$LINT_BUDGET" pre-commit run --files "${CHANGED_FILES[@]}"
    local rc=$?
    # pre-commit runs its remaining hooks after one fails, so an overrun can follow
    # a real failure it already printed: that failure still blocks.
    local failed_hook=$'\\.\\.\\.(\033\\[[0-9;]*m)*Failed'
    if [[ $rc -eq 124 && $CHECK_OUTPUT =~ $failed_hook ]]; then
        return 1
    fi
    [[ $rc -eq 0 || $rc -eq 124 || $rc -eq 125 ]] && return $rc
    return 1
}

# ── Tier 1 fallback: ruff on changed Python files (only when pre-commit is
#    not configured for this repo). ──────────────────────────────────────────
run_ruff_fallback() {
    cd "$REPO_ROOT" || return 0
    local ruff_bin
    for ruff_bin in .venv/bin/ruff venv/bin/ruff; do
        if [[ -x "$ruff_bin" ]]; then
            with_budget "$LINT_BUDGET" "$ruff_bin" check "${PY_FILES[@]}"
            return $?
        fi
    done
    if command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
        with_budget "$LINT_BUDGET" uv run --no-sync --quiet ruff check "${PY_FILES[@]}"
        return $?
    fi
    WARNINGS+=$'\n  - ruff: no pinned version available (no pre-commit config, no .venv, no uv). System ruff skipped to avoid version drift.'
    return 0
}

echo "[pre-push] pre-commit on ${#CHANGED_FILES[@]} changed file(s)…" >&2
run_precommit
rc=$?
if [[ $rc -eq 99 ]]; then
    if [[ ${#PY_FILES[@]} -gt 0 ]]; then
        echo "[pre-push] ruff fallback on ${#PY_FILES[@]} changed Python file(s)…" >&2
        run_ruff_fallback
        rc=$?
        if [[ $rc -eq 124 ]]; then
            WARNINGS+=$'\n'"  - ruff did not finish within ${LINT_BUDGET}s; the push proceeds unchecked by lint — run ruff on the changed Python files locally"
        elif [[ $rc -eq 125 ]]; then
            FAILURES+=$'\n  - ruff could not run: deadline marker setup failed'
        elif [[ $rc -ne 0 ]]; then
            FAILURES+=$'\n  - ruff failed on changed Python files'
        fi
    fi
elif [[ $rc -eq 124 ]]; then
    WARNINGS+=$'\n'"  - pre-commit did not finish within ${LINT_BUDGET}s; the push proceeds unchecked by lint — run pre-commit on the changed files locally"
elif [[ $rc -eq 125 ]]; then
    FAILURES+=$'\n  - pre-commit could not run: deadline marker setup failed'
elif [[ $rc -ne 0 ]]; then
    FAILURES+=$'\n  - pre-commit failed on changed files (lint/format/type-check). If it modified files, commit the result and retry.'
fi

# ── Tier 2: pytest on changed test files ────────────────────────────────────
run_pytest() {
    cd "$REPO_ROOT" || return 0
    local pytest_cmd=() candidate
    for candidate in .venv/bin/pytest venv/bin/pytest; do
        if [[ -x "$candidate" ]]; then
            pytest_cmd=("$candidate")
            break
        fi
    done
    if [[ ${#pytest_cmd[@]} -eq 0 ]] && command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
        pytest_cmd=(uv run --no-sync --quiet pytest)
    fi
    if [[ ${#pytest_cmd[@]} -eq 0 ]]; then
        WARNINGS+=$'\n  - pytest: no repo-pinned pytest found, skipping test-file run'
        return 0
    fi
    with_budget "$TEST_BUDGET" "${pytest_cmd[@]}" -x --no-header -q "${TEST_FILES[@]}"
}

if [[ ${#TEST_FILES[@]} -gt 0 ]]; then
    echo "[pre-push] pytest on ${#TEST_FILES[@]} changed test file(s)…" >&2
    run_pytest
    rc=$?
    if [[ $rc -eq 124 ]]; then
        WARNINGS+=$'\n'"  - pytest did not finish within ${TEST_BUDGET}s; the push proceeds with those tests unrun — run pytest on the changed test files locally"
    elif [[ $rc -eq 125 ]]; then
        FAILURES+=$'\n  - pytest could not run: deadline marker setup failed'
    elif [[ $rc -ne 0 ]]; then
        FAILURES+=$'\n  - pytest failed on changed test files'
    fi
fi

# ── Decision ────────────────────────────────────────────────────────────────
if [[ -n "$FAILURES" ]]; then
    {
        echo ""
        echo "BLOCKED: pre-push validation failed:$FAILURES"
        if [[ -n "$WARNINGS" ]]; then
            echo ""
            echo "Warnings:$WARNINGS"
        fi
        echo ""
        echo "Fix the failures and push again. If they cannot be fixed here, stop and ask the user; only the user can skip this check."
    } >&2
    exit 2
fi

if [[ -n "$WARNINGS" ]]; then
    emit_context "pre-push validation passed with warnings:$WARNINGS"
fi

exit 0
