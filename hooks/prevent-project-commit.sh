#!/bin/bash
#
# prevent-project-commit.sh — provider-neutral PreToolUse hook (wrapper)
#
# The git guard: blocks unsafe git flags, force-pushes to main/master, commits
# of local workflow state or .ai-toolkit/, and `gh pr ready`/`gh pr merge`
# without the user's AITK_PR_READY=1. The logic and its known limits live in
# aitk/hooks/git_guard.py.
#
# Exit codes: 0 allow, 2 block (reason on stderr). Fails closed when python3
# is missing or cannot run the guard, on commands that mention git or gh (N15).

INPUT=$(cat)
COMMAND=$INPUT
if [[ $INPUT =~ \"command\"[[:space:]]*:[[:space:]]*\"(([^\"\\]|\\.)*)\" ]]; then
    COMMAND=${BASH_REMATCH[1]}
fi
GUARDED=0
[[ $COMMAND =~ (^|[^[:alnum:]_])(git|gh)([^[:alnum:]_]|$) ]] && GUARDED=1

if ! command -v python3 >/dev/null 2>&1; then
    [[ "$GUARDED" -eq 0 ]] && exit 0
    echo "BLOCKED: python3 is not on PATH, so the git guard cannot check this git or gh command. Install Python 3.11 or newer (bin/aitk needs it too); do not work around the hook." >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Run from the toolkit root so a module in the project directory cannot shadow it.
printf '%s' "$INPUT" | (cd "$ROOT" && PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m aitk.hooks.git_guard)
status=$?
[[ "$status" -eq 0 || "$status" -eq 2 ]] && exit "$status"
[[ "$GUARDED" -eq 0 ]] && exit 0
echo "BLOCKED: the git guard could not run (exit $status). Stop and ask the user; do not work around the hook." >&2
exit 2
