#!/bin/bash
#
# check-resources.sh — provider-neutral PreToolUse hook
#
# Warns when test runners are invoked with constrained resources.
# Advisory only: always exits 0 (never blocks).
#
# Exit codes:
#   0 — always (warnings go to stderr as model context)
#

set -euo pipefail

# Always allow — this hook only warns
trap 'exit 0' ERR

# Read JSON from stdin
INPUT=$(cat)

# Extract command (fail silently if jq unavailable)
if ! command -v jq &>/dev/null; then
    exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0

# This hook is scoped to potentially parallel test runners.
if ! echo "$COMMAND" | grep -qE '(^|[[:space:]])(jest|pytest|playwright|npm[[:space:]]+test|pnpm[[:space:]]+test|yarn[[:space:]]+test)([[:space:]]|$)'; then
    exit 0
fi

# Skip if worker limit already specified
if echo "$COMMAND" | grep -qE '\-\-maxWorkers|\-n [0-9]|\-w [0-9]|--workers'; then
    exit 0
fi

# Measure available host memory instead of treating container count as load.
AVAILABLE_MB=""
if [[ -r /proc/meminfo ]]; then
    AVAILABLE_KB=$(awk '/^MemAvailable:/ { print $2; exit }' /proc/meminfo)
    if [[ "$AVAILABLE_KB" =~ ^[0-9]+$ ]]; then
        AVAILABLE_MB=$((AVAILABLE_KB / 1024))
    fi
elif command -v vm_stat &>/dev/null; then
    PAGE_SIZE=$(vm_stat | awk 'NR == 1 { gsub("[^0-9]", "", $8); print $8 }')
    AVAILABLE_PAGES=$(vm_stat | awk '
        /Pages free|Pages inactive|Pages speculative/ {
            gsub("\\.", "", $NF); pages += $NF
        }
        END { print pages + 0 }
    ')
    if [[ "$PAGE_SIZE" =~ ^[0-9]+$ && "$AVAILABLE_PAGES" =~ ^[0-9]+$ ]]; then
        AVAILABLE_MB=$((AVAILABLE_PAGES * PAGE_SIZE / 1024 / 1024))
    fi
fi

if [[ "$AVAILABLE_MB" =~ ^[0-9]+$ ]] && (( AVAILABLE_MB < 4096 )); then
    echo "Warning: about ${AVAILABLE_MB} MB host memory is available. Set an explicit low worker count before this test run." >&2
fi

exit 0
