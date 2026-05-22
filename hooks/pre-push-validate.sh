#!/bin/bash
#
# pre-push-validate.sh — Claude Code PreToolUse hook
#
# Runs lint + targeted tests on the commits that are about to be pushed,
# using the repo's pinned tool versions (not the system's). Blocks the push
# only on hard failures. Fail-open on any unexpected error.
#
# Tiers:
#   1. pre-commit on all changed files (preferred — runs the repo's full
#      pinned hook set: ruff, mypy, prettier, oxlint, eslint, tsc, etc.).
#      Fallback for repos without .pre-commit-config.yaml or `pre-commit`:
#      ruff on changed *.py files via repo venv > uv run > skip.
#   2. pytest on changed test files, time-boxed via the repo's venv
#
# Bypass:
#   - Prefix the command:           SKIP_PRECHECK=1 git push ...
#   - Env at Claude Code start:     SKIP_PRECHECK=1
#
# Exit codes:
#   0 — allow
#   2 — block (validation failed, message printed to stderr)
#

set -uo pipefail

# Fail open on any unexpected error
trap 'exit 0' ERR

INPUT=$(cat)

command -v jq      >/dev/null 2>&1 || exit 0
command -v git     >/dev/null 2>&1 || exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
CWD=$(echo     "$INPUT" | jq -r '.cwd // empty'                2>/dev/null) || exit 0

[[ -z "$COMMAND" || -z "$CWD" ]] && exit 0
[[ ! -d "$CWD" ]] && exit 0

# Fast-exit if this isn't a `git push`. Keeps every other Bash call cheap.
# Conservative match: word-boundary git, then push as a later token. The
# safety hook (prevent-project-commit.sh) already handles obfuscated forms.
if ! echo "$COMMAND" | grep -Eq '(^|[^[:alnum:]_/-])git([[:space:]]+(-[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|-C[[:space:]]+[^[:space:]]+))*[[:space:]]+push([[:space:]]|$)'; then
    exit 0
fi

# Bypass — explicit user opt-out
if [[ -n "${SKIP_PRECHECK:-}" ]] || echo "$COMMAND" | grep -q 'SKIP_PRECHECK=1'; then
    exit 0
fi

# Must be inside a git repo
GIT_DIR=$(git -C "$CWD" rev-parse --git-dir 2>/dev/null) || exit 0
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
CHANGED=$(git -C "$REPO_ROOT" diff --name-only --diff-filter=ACMR "$RANGE" 2>/dev/null | \
    while IFS= read -r f; do [[ -f "$REPO_ROOT/$f" ]] && echo "$f"; done)

[[ -z "$CHANGED" ]] && exit 0

# Filter sets
PY_FILES=$(echo "$CHANGED" | grep -E '\.py$' || true)
TEST_FILES=$(echo "$CHANGED" | grep -E '(^|/)test_[^/]+\.py$|(^|/)tests?/.*\.py$|.*_test\.py$' || true)

# Convert newlines to space-separated args for tool invocations
files_args() {
    echo "$1" | tr '\n' ' '
}

FAILURES=""
WARNINGS=""

# ── Tier 1: lint/format/type-check via the repo's pinned hooks ──────────────
#
# Returns:
#   0  — ran and passed (or nothing to do)
#   1  — ran and failed (block the push)
#   99 — not configured here, caller should try the fallback path
run_precommit() {
    local files="$1"
    [[ -z "$files" ]] && return 0

    cd "$REPO_ROOT" || return 99
    [[ -f .pre-commit-config.yaml ]] || return 99
    command -v pre-commit >/dev/null 2>&1 || {
        WARNINGS+=$'\n  - pre-commit config present but `pre-commit` not installed — install it so push-time lint matches CI.'
        return 99
    }

    local args; args=$(files_args "$files")
    local timeout_cmd=""
    command -v gtimeout >/dev/null 2>&1 && timeout_cmd="gtimeout 240"

    # `--files` makes pre-commit operate on these files regardless of stage
    # gating. Each hook's own `files:` regex filters down further, so hooks
    # that don't match the changed set no-op. Exit 1 covers both "hook
    # failed" and "hook modified files" — both should block the push.
    # shellcheck disable=SC2086
    $timeout_cmd pre-commit run --files $args >&2
    local rc=$?

    if [[ $rc -eq 124 ]]; then
        WARNINGS+=$'\n  - pre-commit: exceeded 240s — not blocking, run locally to verify.'
        return 0
    fi
    return $rc
}

# ── Tier 1 fallback: ruff on changed Python files (only when pre-commit is
#    not configured for this repo). ──────────────────────────────────────────
run_ruff_fallback() {
    local files="$1"
    [[ -z "$files" ]] && return 0

    cd "$REPO_ROOT" || return 0

    for ruff_bin in .venv/bin/ruff venv/bin/ruff; do
        if [[ -x "$ruff_bin" ]]; then
            local args; args=$(files_args "$files")
            # shellcheck disable=SC2086
            "$ruff_bin" check $args >&2 || return 1
            return 0
        fi
    done

    if command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
        local args; args=$(files_args "$files")
        # shellcheck disable=SC2086
        uv run --no-sync --quiet ruff check $args >&2 || return 1
        return 0
    fi

    WARNINGS+=$'\n  - ruff: no pinned version available (no pre-commit config, no .venv, no uv). System ruff skipped to avoid version drift.'
    return 0
}

if [[ -n "$CHANGED" ]]; then
    n_changed=$(echo "$CHANGED" | wc -l | tr -d ' ')
    echo "[pre-push] pre-commit on $n_changed changed file(s)…" >&2
    run_precommit "$CHANGED"
    rc=$?
    if [[ $rc -eq 99 ]]; then
        # No pre-commit available — fall back to Python-only ruff
        if [[ -n "$PY_FILES" ]]; then
            n_py=$(echo "$PY_FILES" | wc -l | tr -d ' ')
            echo "[pre-push] ruff fallback on $n_py changed Python file(s)…" >&2
            if ! run_ruff_fallback "$PY_FILES"; then
                FAILURES+=$'\n  - ruff failed on changed Python files'
            fi
        fi
    elif [[ $rc -ne 0 ]]; then
        FAILURES+=$'\n  - pre-commit failed on changed files (lint/format/type-check). If it modified files, commit the result and retry.'
    fi
fi

# ── Tier 2: pytest on changed test files ────────────────────────────────────
run_pytest() {
    local files="$1"
    [[ -z "$files" ]] && return 0

    cd "$REPO_ROOT" || return 0

    local pytest_cmd=""
    for p in .venv/bin/pytest venv/bin/pytest; do
        if [[ -x "$p" ]]; then
            pytest_cmd="$p"
            break
        fi
    done
    if [[ -z "$pytest_cmd" ]] && command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
        pytest_cmd="uv run --no-sync --quiet pytest"
    fi
    if [[ -z "$pytest_cmd" ]]; then
        WARNINGS+=$'\n  - pytest: no repo-pinned pytest found, skipping test-file run'
        return 0
    fi

    local args; args=$(files_args "$files")
    local timeout_cmd=""
    command -v gtimeout >/dev/null 2>&1 && timeout_cmd="gtimeout 120"

    # shellcheck disable=SC2086
    $timeout_cmd $pytest_cmd -x --no-header -q $args >&2
    local rc=$?
    if [[ $rc -eq 124 ]]; then
        WARNINGS+=$'\n  - pytest: changed test files exceeded 120s — not blocking, verify locally'
        return 0
    fi
    return $rc
}

if [[ -n "$TEST_FILES" ]]; then
    echo "[pre-push] pytest on $(echo "$TEST_FILES" | wc -l | tr -d ' ') changed test file(s)…" >&2
    if ! run_pytest "$TEST_FILES"; then
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
        echo "Fix the failures above, or bypass for this push:"
        echo "    SKIP_PRECHECK=1 git push ..."
    } >&2
    exit 2
fi

if [[ -n "$WARNINGS" ]]; then
    {
        echo ""
        echo "[pre-push] passed with warnings:$WARNINGS"
    } >&2
fi

exit 0
