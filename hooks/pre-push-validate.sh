#!/bin/bash
#
# pre-push-validate.sh — provider-neutral PreToolUse hook
#
# Runs lint + targeted tests on the commits that are about to be pushed,
# using the repo's pinned tool versions (not the system's). Blocks the push
# on a failure or a check that runs out of time.
#
# Tiers:
#   1. pre-commit on all changed files (preferred — runs the repo's full
#      pinned hook set: ruff, mypy, prettier, oxlint, eslint, tsc, etc.).
#      Fallback for repos without .pre-commit-config.yaml or `pre-commit`:
#      ruff on changed *.py files via repo venv > uv run > skip.
#   2. pytest on changed test files via the repo's venv.
#
# Time budgets: lint 180 s, tests 90 s, each with a 5 s grace before KILL,
# so both together stay under the 300 s hook timeout in hooks/hooks.json. A
# hook the runtime kills at its own timeout lets the push through; a check
# that runs out of its budget here blocks it. `timeout` is used when present,
# else `gtimeout`, else a shell watchdog. AITK_PRECHECK_LINT_BUDGET and
# AITK_PRECHECK_TEST_BUDGET can only lower the budgets.
#
# Bypass is the user's alone: SKIP_PRECHECK=1 in the environment Claude Code
# or Codex started with, or as an environment prefix of the `git push`
# itself (`SKIP_PRECHECK=1 git push ...`). The block message never suggests it.
#
# Output:
#   exit 2 — block; the reason (and the tools' output) on stderr.
#   exit 0 — allow; warnings go to stdout as hookSpecificOutput.additionalContext,
#            which the model sees.
# Setup problems (no python3, git, repo or base commit) allow the push.

set -u

INPUT=$(cat)

# Fast exit: most Bash calls are not pushes.
[[ $INPUT == *push* ]] || exit 0

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

# Find the push: the shared tokenizer yields every command with its own env
# prefix, so `SKIP_PRECHECK=1` only counts on the push it precedes.
# Output: "push<TAB>workdir<TAB>skip" for the first push, nothing otherwise.
read -r -d '' PARSER <<'PY'
import json, os, re, sys
from aitk.hooks import shell_tokens

GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"}
try:
    payload = json.loads(sys.stdin.read() or "{}")
except ValueError:
    raise SystemExit(0)
command = (payload.get("tool_input") or {}).get("command") or ""
cwd = payload.get("cwd") or ""
if not (isinstance(command, str) and isinstance(cwd, str) and command and os.path.isdir(cwd)):
    raise SystemExit(0)
pushes = []
for found in shell_tokens.commands(command, cwd):
    if found.unresolved:
        if re.search(r"\bgit\b.*\bpush\b", found.text, re.S):
            pushes.append((found.workdir or cwd, False))
        continue
    if found.name != "git":
        continue
    args = found.argv[1:]
    workdir = found.workdir or cwd
    index = 0
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "-C" and index + 1 < len(args):
            workdir = os.path.join(workdir, args[index + 1])
        index += 2 if args[index] in GIT_VALUE_FLAGS else 1
    if args[index:index + 1] == ["push"]:
        pushes.append((workdir, shell_tokens.truthy(found.assignments.get("SKIP_PRECHECK"))))
pending = [push for push in pushes if not push[1]]
if pending:
    print(f"push\t{pending[0][0]}\t0")
elif pushes:
    print(f"push\t{pushes[0][0]}\t1")
PY

PARSED=$(printf '%s' "$INPUT" | (cd "$ROOT" && PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c "$PARSER")) || exit 0
[[ $PARSED == push$'\t'* ]] || exit 0
IFS=$'\t' read -r _ CWD SKIP_PREFIX <<<"$PARSED"

# Bypass: the user's session env, or a prefix on the push itself.
if [[ "$SKIP_PREFIX" == "1" ]] || [[ -n "${SKIP_PRECHECK:-}" && "${SKIP_PRECHECK}" != "0" && "${SKIP_PRECHECK}" != "false" ]]; then
    exit 0
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

TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_BIN=timeout
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN=gtimeout
fi

# Run "$@" within SECONDS; return 124 when it runs out of time.
with_budget() {
    local seconds=$1
    shift
    if [[ -n "$TIMEOUT_BIN" ]]; then
        "$TIMEOUT_BIN" -k "$GRACE" "$seconds" "$@"
        local rc=$?
        [[ $rc -eq 137 ]] && rc=124
        return $rc
    fi
    local marker
    marker=$(mktemp "${TMPDIR:-/tmp}/aitk-prepush.XXXXXX") || return 1
    rm -f "$marker"
    "$@" &
    local pid=$!
    (
        sleeper=""
        trap '[[ -n "$sleeper" ]] && kill "$sleeper" 2>/dev/null; exit 0' TERM
        sleep "$seconds" &
        sleeper=$!
        wait "$sleeper"
        if kill -0 "$pid" 2>/dev/null; then
            : >"$marker"
            kill -TERM "$pid" 2>/dev/null
            sleep "$GRACE"
            kill -KILL "$pid" 2>/dev/null
        fi
    ) &
    local watchdog=$!
    wait "$pid"
    local rc=$?
    kill -TERM "$watchdog" 2>/dev/null
    wait "$watchdog" 2>/dev/null
    if [[ -e "$marker" ]]; then
        rm -f "$marker"
        return 124
    fi
    return $rc
}

FAILURES=""
WARNINGS=""

# ── Tier 1: lint/format/type-check via the repo's pinned hooks ──────────────
#
# Returns:
#   0   — ran and passed (or nothing to do)
#   1   — ran and failed (block the push)
#   124 — ran out of its budget (block the push)
#   99  — not configured here, caller should try the fallback path
run_precommit() {
    cd "$REPO_ROOT" || return 99
    [[ -f .pre-commit-config.yaml ]] || return 99
    if ! command -v pre-commit >/dev/null 2>&1; then
        WARNINGS+=$'\n  - pre-commit config present but `pre-commit` not installed; install it so push-time lint matches CI.'
        return 99
    fi
    # `--files` makes pre-commit operate on these files regardless of stage
    # gating. Each hook's own `files:` regex filters down further, so hooks
    # that don't match the changed set no-op. Exit 1 covers both "hook
    # failed" and "hook modified files"; both block the push.
    with_budget "$LINT_BUDGET" pre-commit run --files "${CHANGED_FILES[@]}" >&2
    local rc=$?
    [[ $rc -eq 0 || $rc -eq 124 ]] && return $rc
    return 1
}

# ── Tier 1 fallback: ruff on changed Python files (only when pre-commit is
#    not configured for this repo). ──────────────────────────────────────────
run_ruff_fallback() {
    cd "$REPO_ROOT" || return 0
    local ruff_bin
    for ruff_bin in .venv/bin/ruff venv/bin/ruff; do
        if [[ -x "$ruff_bin" ]]; then
            with_budget "$LINT_BUDGET" "$ruff_bin" check "${PY_FILES[@]}" >&2
            return $?
        fi
    done
    if command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
        with_budget "$LINT_BUDGET" uv run --no-sync --quiet ruff check "${PY_FILES[@]}" >&2
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
            FAILURES+=$'\n'"  - ruff did not finish within ${LINT_BUDGET}s"
        elif [[ $rc -ne 0 ]]; then
            FAILURES+=$'\n  - ruff failed on changed Python files'
        fi
    fi
elif [[ $rc -eq 124 ]]; then
    FAILURES+=$'\n'"  - pre-commit did not finish within ${LINT_BUDGET}s; run it locally on the changed files"
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
    with_budget "$TEST_BUDGET" "${pytest_cmd[@]}" -x --no-header -q "${TEST_FILES[@]}" >&2
}

if [[ ${#TEST_FILES[@]} -gt 0 ]]; then
    echo "[pre-push] pytest on ${#TEST_FILES[@]} changed test file(s)…" >&2
    run_pytest
    rc=$?
    if [[ $rc -eq 124 ]]; then
        FAILURES+=$'\n'"  - pytest did not finish within ${TEST_BUDGET}s on the changed test files"
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
