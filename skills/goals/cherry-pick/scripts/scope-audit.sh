#!/usr/bin/env bash
#
# scope-audit.sh — mechanical pre-check for cherry-pick scope leak.
#
# Compares the source commit's diff against the cherry-pick result (HEAD^..HEAD)
# and flags extra files, missing files, and per-file line-count divergence.
#
# Usage: scope-audit.sh <source-commit-sha>
#
# Exit codes:
#   0 = clean (no extra files, no significant divergence)
#   1 = flagged (extra files or >20% divergence — investigate in Step 2)
#   2 = invocation error
#
# This script produces mechanical signals only. The calling workflow must still
# run the LLM hunk-level audit (Step 2 in references/validate.md).

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <source-commit-sha>" >&2
  exit 2
fi

SOURCE_COMMIT="$1"

if ! git rev-parse --verify "${SOURCE_COMMIT}^{commit}" >/dev/null 2>&1; then
  echo "error: ${SOURCE_COMMIT} is not a valid commit" >&2
  exit 2
fi

SOURCE_FILES=$(git diff --name-only "${SOURCE_COMMIT}^..${SOURCE_COMMIT}" | sort)
RESULT_FILES=$(git diff --name-only HEAD^..HEAD | sort)

EXTRA_FILES=$(comm -13 <(echo "$SOURCE_FILES") <(echo "$RESULT_FILES") || true)
MISSING_FILES=$(comm -23 <(echo "$SOURCE_FILES") <(echo "$RESULT_FILES") || true)
SHARED_FILES=$(comm -12 <(echo "$SOURCE_FILES") <(echo "$RESULT_FILES") || true)

SOURCE_COUNT=$(printf '%s\n' "$SOURCE_FILES" | grep -c . || true)
RESULT_COUNT=$(printf '%s\n' "$RESULT_FILES" | grep -c . || true)

echo "## Scope Audit — Mechanical Pre-Check"
echo
echo "Source commit: $SOURCE_COMMIT"
echo "Files in source: $SOURCE_COUNT | Files in cherry-pick: $RESULT_COUNT"
echo

FLAGGED=0

if [[ -n "$EXTRA_FILES" ]]; then
  echo "### Extra files (in cherry-pick but not source) — SCOPE LEAK UNTIL PROVEN OTHERWISE"
  echo "$EXTRA_FILES" | sed 's/^/  - /'
  echo
  FLAGGED=1
else
  echo "Extra files: none"
fi

if [[ -n "$MISSING_FILES" ]]; then
  echo "### Missing files (in source but not cherry-pick) — may be legitimate exclusions"
  echo "$MISSING_FILES" | sed 's/^/  - /'
  echo
else
  echo "Missing files: none"
fi

echo
echo "### Per-file line-count comparison (shared files)"
echo "Threshold: flag when divergence > 20%"
echo

while IFS= read -r f; do
  [[ -z "$f" ]] && continue

  SRC_LINES=$(git diff --numstat "${SOURCE_COMMIT}^..${SOURCE_COMMIT}" -- "$f" | awk '{print $1 + $2}')
  RES_LINES=$(git diff --numstat HEAD^..HEAD -- "$f" | awk '{print $1 + $2}')

  SRC_LINES=${SRC_LINES:-0}
  RES_LINES=${RES_LINES:-0}

  if [[ "$SRC_LINES" -eq 0 ]]; then
    DIVERGENCE="n/a (source=0)"
    FLAG=""
  else
    DIFF=$(( RES_LINES - SRC_LINES ))
    ABS_DIFF=${DIFF#-}
    PCT=$(( ABS_DIFF * 100 / SRC_LINES ))
    DIVERGENCE="${PCT}%"
    if [[ "$PCT" -gt 20 ]]; then
      FLAG="  ⚠ FLAGGED"
      FLAGGED=1
    else
      FLAG=""
    fi
  fi

  echo "  $f | source: $SRC_LINES | result: $RES_LINES | Δ: $DIVERGENCE$FLAG"
done <<< "$SHARED_FILES"

echo

if [[ "$FLAGGED" -eq 1 ]]; then
  echo "Mechanical verdict: FLAGGED — investigate flagged items in Step 2 (LLM hunk audit)"
  exit 1
else
  echo "Mechanical verdict: CLEAN — still run Step 2 (LLM hunk audit), but with higher confidence"
  exit 0
fi
