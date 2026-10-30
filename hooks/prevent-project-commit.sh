#!/bin/bash
#
# prevent-project-commit.sh — provider-neutral PreToolUse hook (wrapper)
#
# The git guard: blocks unsafe git flags, force-pushes to main/master, commits
# of local workflow state or .ai-toolkit/, and `gh pr ready`/`gh pr merge`
# without the user's AITK_PR_READY=1 from the session environment, and any
# command that sets or exports an override itself. The logic and its known
# limits live in hooks/lib/git_guard.py.
#
# Exit codes: 0 allow, 2 block (reason on stderr). Fails closed when python3
# is missing or cannot run the guard, on commands that mention git, gh or an
# override variable (N15).

INPUT=$(cat)
COMMAND=$INPUT
if [[ $INPUT =~ \"command\"[[:space:]]*:[[:space:]]*\"(([^\"\\]|\\.)*)\" ]]; then
    COMMAND=${BASH_REMATCH[1]}
fi
GUARDED=0
# git and gh in any case (`GIT`, `Gh`): the filesystem may ignore it
[[ $COMMAND =~ (^|[^[:alnum:]_])([Gg][Ii][Tt]|[Gg][Hh])([^[:alnum:]_]|$)|AITK_PR_READY|SKIP_PR_GATE|SKIP_PRECHECK ]] && GUARDED=1

if ! command -v python3 >/dev/null 2>&1; then
    [[ "$GUARDED" -eq 0 ]] && exit 0
    echo "BLOCKED: python3 is not on PATH, so the git guard cannot check this command. Install Python 3.11 or newer; do not work around the hook." >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# -E ignores PYTHONPATH and -s the user site, so only hooks/lib (the script's
# own directory) supplies imports; the project directory cannot shadow them.
printf '%s' "$INPUT" | python3 -E -s "$ROOT/hooks/lib/git_guard.py"
status=$?
[[ "$status" -eq 0 || "$status" -eq 2 ]] && exit "$status"
[[ "$GUARDED" -eq 0 ]] && exit 0
echo "BLOCKED: the git guard could not run (exit $status). Stop and ask the user; do not work around the hook." >&2
exit 2
