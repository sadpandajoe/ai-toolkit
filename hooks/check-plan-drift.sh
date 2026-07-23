#!/bin/bash
#
# check-plan-drift.sh — provider-neutral Stop hook
#
# Warns when PLAN.md has been modified significantly more recently than
# PROJECT.md, suggesting active work that hasn't updated the state file.
#
# Fail-open: exits 0 on any unexpected state (never blocks on errors).
# Threshold: 30 minutes — avoids noise during active editing.
#

set -euo pipefail
trap 'exit 0' ERR

INPUT=$(cat)

if ! command -v jq &>/dev/null; then
    exit 0
fi

CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null) || exit 0

if [[ -z "$CWD" ]] || ! cd "$CWD" 2>/dev/null; then
    exit 0
fi

# Both files must exist for drift to be meaningful
if [[ ! -f PLAN.md ]] || [[ ! -f PROJECT.md ]]; then
    exit 0
fi

# Compare mtimes (portable: stat -f on macOS, stat -c on Linux)
if stat -f %m PLAN.md &>/dev/null; then
    PLAN_MTIME=$(stat -f %m PLAN.md)
    PROJECT_MTIME=$(stat -f %m PROJECT.md)
else
    PLAN_MTIME=$(stat -c %Y PLAN.md)
    PROJECT_MTIME=$(stat -c %Y PROJECT.md)
fi

DELTA=$((PLAN_MTIME - PROJECT_MTIME))

# 1800 seconds = 30 minutes. Only warn if PLAN.md is significantly newer.
if (( DELTA > 1800 )); then
    cat >&2 <<EOF
[plan-drift] PLAN.md is $((DELTA / 60)) minutes newer than PROJECT.md.
PROJECT.md should reflect current state. Update it before the workflow ends.
EOF
fi

exit 0
