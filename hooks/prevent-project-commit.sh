#!/bin/bash
#
# prevent-project-commit.sh — provider-neutral PreToolUse hook (wrapper)
#
# The git guard: blocks unsafe git flags, force-pushes to main/master, commits
# of local workflow state or .ai-toolkit/, `gh pr ready`/`gh pr merge` and a
# non-draft PR without the user's AITK_PR_READY=1 from the session environment,
# `gh pr create` without a passing scripts/verify.py record on its tree (no
# override lifts that one), and any command that sets or exports an override
# itself. The logic and its known limits live in hooks/lib/git_guard.py.
#
# Exit codes: 0 allow, 2 block (reason on stderr). Fails closed when python3
# is missing or cannot run the guard, on commands that mention git, gh or an
# override variable (N15).

INPUT=$(cat)
COMMAND=$INPUT
if [[ $INPUT =~ \"command\"[[:space:]]*:[[:space:]]*\"(([^\"\\]|\\.)*)\" ]]; then
    COMMAND=${BASH_REMATCH[1]}
fi
GUARD_WORDS='(^|[^[:alnum:]_])([Gg][Ii][Tt]|[Gg][Hh])([^[:alnum:]_]|$)|AITK_PR_READY|SKIP_PRECHECK'
# git and gh in any case (`GIT`, `Gh`): the filesystem may ignore it
GUARDED=0
[[ $COMMAND =~ $GUARD_WORDS ]] && GUARDED=1
# Only when python cannot run: the same match with the quote characters and backslashes
# removed (`g'i't`). Replacing them in a large command is slow in bash, so it is not done
# on the normal path.
guarded_unquoted() {
    [[ "$GUARDED" -eq 1 ]] && return 0
    local plain=${COMMAND//[\'\"\\\`]/}
    [[ $plain =~ $GUARD_WORDS ]]
}

if ! command -v python3 >/dev/null 2>&1; then
    guarded_unquoted || exit 0
    echo "BLOCKED: python3 is not on PATH, so the git guard cannot check this command. Install Python 3.11 or newer; do not work around the hook." >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# -E ignores PYTHONPATH and -s the user site, so only hooks/lib (the script's
# own directory) supplies imports; the project directory cannot shadow them.
printf '%s' "$INPUT" | python3 -E -s "$ROOT/hooks/lib/git_guard.py"
status=$?
[[ "$status" -eq 0 || "$status" -eq 2 ]] && exit "$status"
guarded_unquoted || exit 0
echo "BLOCKED: the git guard could not run (exit $status). Stop and ask the user; do not work around the hook." >&2
exit 2
