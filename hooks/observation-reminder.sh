#!/bin/bash
#
# observation-reminder.sh — provider-neutral Stop hook
#
# The observation queue (.ai-toolkit/observations.jsonl) is append-only during
# real work and is only read by a deliberate `reflect observations` review.
# Nothing else would ever prompt that review, so this hook counts the
# unreviewed lines and says so once the queue is worth a look.
#
# Fail-open: exits 0 on any unexpected state (never blocks on errors).
# Threshold: 10 unreviewed observations.
#

set -euo pipefail
trap 'exit 0' ERR

THRESHOLD="${AITK_OBSERVATION_THRESHOLD:-10}"

INPUT=$(cat)

if ! command -v jq &>/dev/null; then
    exit 0
fi

CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null) || exit 0

if [[ -z "$CWD" ]] || ! cd "$CWD" 2>/dev/null; then
    exit 0
fi

QUEUE=".ai-toolkit/observations.jsonl"
if [[ ! -f "$QUEUE" ]]; then
    exit 0
fi

# grep -c prints 0 itself when nothing matches (and exits 1), so only guard the exit.
COUNT=$(grep -c '[^[:space:]]' "$QUEUE" 2>/dev/null || true)
COUNT=${COUNT:-0}

if (( COUNT >= THRESHOLD )); then
    cat >&2 <<EOF
[observations] $COUNT unreviewed observations in $QUEUE.
Run \`reflect observations\` to cluster them and propose rule or skill changes.
EOF
fi

exit 0
