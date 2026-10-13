#!/usr/bin/env bash
#
# scope-audit.sh — mechanical pre-check for cherry-pick scope leak.
#
# Compares the exact changed lines of the source commit with those of the
# cherry-pick result, file by file (`git diff -U0`, each + and - line, against
# the first parent so merges work too), and reports:
#   - extra files and extra lines: in the result, not in the source. A leak
#     until proven otherwise; each line shows the source-side commits that
#     added or removed it (`git log -S`, merge-base..source).
#   - missing files and missing lines: in the source, not in the result. An
#     adaptation or an incomplete pick; each line shows the target-side
#     commits that touched it (merge-base..result).
#   - moved code: for each file the source commit adds by moving or copying
#     another file (`git diff -C -C`), lines the result adds that the original
#     file only has on the source side. A neighbouring source commit changed
#     the code before it moved, and the move carries that change along.
#
# Usage: scope-audit.sh [-C <repo>] <source-commit> [<result-commit>]
#   <result-commit> defaults to HEAD.
#
# Exit codes:
#   0 = clean: the result changes exactly the source's lines
#   1 = flagged: extra or missing files or lines, or moved-code candidates —
#       investigate in Step 2
#   2 = invocation error
#
# This script produces mechanical signals only. The calling workflow must still
# run the LLM hunk-level audit (Step 2 in references/validate.md).

set -euo pipefail

REPO="."
if [[ "${1:-}" == "-C" ]]; then
  REPO="${2:?-C needs a repository path}"
  shift 2
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 [-C <repo>] <source-commit> [<result-commit>]" >&2
  exit 2
fi

g() { git -C "$REPO" -c core.quotePath=false "$@"; }

SOURCE_COMMIT="$1"
RESULT_COMMIT="${2:-HEAD}"
for commit in "$SOURCE_COMMIT" "$RESULT_COMMIT"; do
  if ! g rev-parse --verify --quiet "${commit}^{commit}" >/dev/null; then
    echo "error: ${commit} is not a valid commit" >&2
    exit 2
  fi
done
SOURCE=$(g rev-parse "${SOURCE_COMMIT}^{commit}")
RESULT=$(g rev-parse "${RESULT_COMMIT}^{commit}")

parent() {
  if g rev-parse --verify --quiet "$1^1" >/dev/null; then
    g rev-parse "$1^1"
  else
    g hash-object -t tree /dev/null
  fi
}
SOURCE_BASE=$(parent "$SOURCE")
RESULT_BASE=$(parent "$RESULT")
MERGE_BASE=$(g merge-base "$SOURCE" "$RESULT" 2>/dev/null || true)

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Changed lines as "file<TAB>sign<TAB>text", sorted, from a -U0 diff.
changed_lines() {
  # Header lines are read only before a file's first hunk, so a changed line
  # that itself starts with "-- " or "++ " is not taken for one.
  g diff -U0 --no-color --no-ext-diff --no-renames "$1" "$2" | LC_ALL=C awk '
    /^diff --git / { file = ""; header = 1; next }
    header && /^--- / { old = substr($0, 5); sub(/^a\//, "", old); next }
    header && /^\+\+\+ / {
      new = substr($0, 5); sub(/^b\//, "", new)
      file = (new == "/dev/null") ? old : new
      next
    }
    /^@@/ { header = 0; next }
    !header && file != "" && /^[+-]/ { print file "\t" substr($0, 1, 1) "\t" substr($0, 2) }
  ' | LC_ALL=C sort
}

changed_lines "$SOURCE_BASE" "$SOURCE" > "$WORK_DIR/source"
changed_lines "$RESULT_BASE" "$RESULT" > "$WORK_DIR/result"
cut -f1 "$WORK_DIR/source" | LC_ALL=C sort -u > "$WORK_DIR/source_files"
cut -f1 "$WORK_DIR/result" | LC_ALL=C sort -u > "$WORK_DIR/result_files"
g diff --name-only --no-renames "$SOURCE_BASE" "$SOURCE" | LC_ALL=C sort -u >> "$WORK_DIR/source_files"
g diff --name-only --no-renames "$RESULT_BASE" "$RESULT" | LC_ALL=C sort -u >> "$WORK_DIR/result_files"
LC_ALL=C sort -u -o "$WORK_DIR/source_files" "$WORK_DIR/source_files"
LC_ALL=C sort -u -o "$WORK_DIR/result_files" "$WORK_DIR/result_files"

EXTRA_FILES=$(LC_ALL=C comm -13 "$WORK_DIR/source_files" "$WORK_DIR/result_files")
MISSING_FILES=$(LC_ALL=C comm -23 "$WORK_DIR/source_files" "$WORK_DIR/result_files")
LC_ALL=C comm -13 "$WORK_DIR/source" "$WORK_DIR/result" > "$WORK_DIR/extra"
LC_ALL=C comm -23 "$WORK_DIR/source" "$WORK_DIR/result" > "$WORK_DIR/missing"

ORIGIN_LIMIT=20

# The commits in RANGE that added or removed TEXT in FILE.
origin() {
  local text=$1 file=$2 range=$3 trimmed found
  trimmed=$(printf '%s' "$text" | tr -d '[:space:]')
  if [[ ${#trimmed} -lt 4 ]]; then
    echo "(too short to trace)"
    return
  fi
  found=$(g log -S"$text" --format='%h %s' -n 3 "$range" -- "$file" 2>/dev/null || true)
  if [[ -z "$found" ]]; then
    echo "(no commit in $range)"
  else
    printf '%s' "$found" | paste -sd ';' - | sed 's/;/; /g'
  fi
}

# Print one line set with origins: FILE, RANGE for the git log -S lookup.
report_lines() {
  local list=$1 range=$2 count=0 file sign text
  while IFS=$'\t' read -r file sign text; do
    count=$((count + 1))
    if [[ $count -le $ORIGIN_LIMIT ]]; then
      printf '  %s: %s%s\n      origin: %s\n' "$file" "$sign" "$text" "$(origin "$text" "$file" "$range")"
    else
      printf '  %s: %s%s\n' "$file" "$sign" "$text"
    fi
  done < "$list"
}

echo "## Scope Audit — Mechanical Pre-Check"
echo
echo "Source commit: $SOURCE_COMMIT ($(g rev-parse --short "$SOURCE"))"
echo "Result commit: $RESULT_COMMIT ($(g rev-parse --short "$RESULT"))"
echo "Files in source: $(grep -c . "$WORK_DIR/source_files" || true) | Files in result: $(grep -c . "$WORK_DIR/result_files" || true)"
echo "Changed lines in source: $(grep -c '' "$WORK_DIR/source" || true) | in result: $(grep -c '' "$WORK_DIR/result" || true)"
echo

FLAGGED=0

if [[ -n "$EXTRA_FILES" ]]; then
  echo "### Extra files (in result but not source) — SCOPE LEAK UNTIL PROVEN OTHERWISE"
  echo "$EXTRA_FILES" | sed 's/^/  - /'
  echo
  FLAGGED=1
else
  echo "Extra files: none"
fi

if [[ -n "$MISSING_FILES" ]]; then
  echo "### Missing files (in source but not result) — may be legitimate exclusions"
  echo "$MISSING_FILES" | sed 's/^/  - /'
  echo
  FLAGGED=1
else
  echo "Missing files: none"
fi
echo

SOURCE_RANGE="${MERGE_BASE:+$MERGE_BASE..}$SOURCE"
RESULT_RANGE="${MERGE_BASE:+$MERGE_BASE..}$RESULT"

if [[ -s "$WORK_DIR/extra" ]]; then
  echo "### Extra lines (changed in result, not in source) — SCOPE LEAK UNTIL PROVEN OTHERWISE"
  echo "Origin: source-side commits that added or removed the line ($SOURCE_RANGE)."
  report_lines "$WORK_DIR/extra" "$SOURCE_RANGE"
  echo
  FLAGGED=1
else
  echo "Extra lines: none"
fi

if [[ -s "$WORK_DIR/missing" ]]; then
  echo "### Missing lines (changed in source, not in result) — adaptation or incomplete pick"
  echo "Origin: target-side commits that added or removed the line ($RESULT_RANGE)."
  report_lines "$WORK_DIR/missing" "$RESULT_RANGE"
  echo
  FLAGGED=1
else
  echo "Missing lines: none"
fi
echo

# Moved code: files the source commit creates from another file.
echo "### Moved-code check (files the source commit adds by move or copy)"
MOVED=0
while IFS=$'\t' read -r status old new; do
  [[ $status == R* || $status == C* ]] || continue
  [[ -n "$new" ]] || continue
  MOVED=1
  if ! g cat-file -e "$RESULT_BASE:$old" 2>/dev/null; then
    echo "  $new (from $old): $old does not exist on the target base — the moved code may carry changes the target never had; review it whole"
    FLAGGED=1
    continue
  fi
  # Lines the original file has on the source side but not on the target base:
  # changes from neighbouring source commits.
  g diff -U0 --no-color --no-ext-diff "$RESULT_BASE:$old" "$SOURCE_BASE:$old" \
    | awk '/^@@/ { body = 1; next } body && /^\+/ { print substr($0, 2) }' | LC_ALL=C sort -u > "$WORK_DIR/neighbour"
  awk -F'\t' -v file="$new" '$1 == file && $2 == "+" { print substr($0, length($1) + 4) }' "$WORK_DIR/result" \
    | LC_ALL=C sort -u > "$WORK_DIR/moved_added"
  CARRIED=$(LC_ALL=C comm -12 "$WORK_DIR/neighbour" "$WORK_DIR/moved_added" | awk 'length($0) > 0')
  if [[ -n "$CARRIED" ]]; then
    echo "  $new (from $old): lines a neighbouring source commit changed before the move — MOVED-CODE LEAK UNTIL PROVEN OTHERWISE"
    while IFS= read -r text; do
      printf '      +%s\n      origin: %s\n' "$text" "$(origin "$text" "$old" "$SOURCE_RANGE")"
    done <<< "$CARRIED"
    FLAGGED=1
  else
    echo "  $new (from $old): no neighbour changes carried"
  fi
done < <(g diff --name-status -C -C --diff-filter=RC "$SOURCE_BASE" "$SOURCE")
[[ $MOVED -eq 0 ]] && echo "  none (the source commit moves or copies no file)"
echo

if [[ "$FLAGGED" -eq 1 ]]; then
  echo "Mechanical verdict: FLAGGED — investigate flagged items in Step 2 (LLM hunk audit)"
  exit 1
else
  echo "Mechanical verdict: CLEAN — still run Step 2 (LLM hunk audit), but with higher confidence"
  exit 0
fi
