#!/bin/bash
#
# require-review-gate.sh — provider-neutral PreToolUse hook (wrapper)
#
# `gh pr create` needs a review PASS backed by a reviewer record and `--draft`; the logic, its
# overrides (SKIP_PR_GATE=1 lifts the review check, AITK_PR_READY=1 the draft
# check; both count only from the session environment) and its known limits
# live in aitk/hooks/review_gate.py.
#
# Exit codes: 0 allow, 2 block (reason on stderr). Fails closed when python3
# is missing or cannot run the gate, on the commands the prefilter selects (N15).

INPUT=$(cat)
COMMAND=$INPUT
if [[ $INPUT =~ \"command\"[[:space:]]*:[[:space:]]*\"(([^\"\\]|\\.)*)\" ]]; then
    COMMAND=${BASH_REMATCH[1]}
fi

# Prefilter: `gh ... create`/`gh ... new` opens a PR the hook checks. A command that
# mentions `deliver` goes to the detector too: `aitk deliver` itself always opens a
# draft and has no ready flag, but its arguments can nest a creation the text
# match cannot see (`--title "$(g'h' pr create --fill)"`), so the tokenizer reads them.
# Each test is one `*word*` pattern, linear in the command length: a pattern with
# two stars backtracks quadratically, and this runs before the Python deadline.
if [[ $COMMAND != *deliver* ]]; then
    [[ $COMMAND == *[Gg][Hh]* ]] || exit 0
    [[ $COMMAND == *create* || $COMMAND == *new* ]] || exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "BLOCKED: python3 is not on PATH, so the review gate cannot check this PR command. Install Python 3.11 or newer (bin/aitk needs it too); do not work around the hook." >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Run from the toolkit root so a module in the project directory cannot shadow it.
printf '%s' "$INPUT" | (cd "$ROOT" && PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m aitk.hooks.review_gate)
status=$?
[[ "$status" -eq 0 || "$status" -eq 2 ]] && exit "$status"
echo "BLOCKED: the review gate could not run (exit $status). Stop and ask the user; do not work around the hook." >&2
exit 2
