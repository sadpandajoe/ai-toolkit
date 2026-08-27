#!/usr/bin/env bash
#
# batch-deps.sh — file-overlap analysis for cherry-pick batches.
#
# Given a list of source SHAs (must be reachable in the local git repo), emits
# the mechanical signals needed to build a real dependency-aware execution order:
#
#   1. Per-SHA file lists (author-date order, oldest first)
#   2. SHA pairs that share files (dependency edges; the earlier one should
#      generally come first, but verify by inspecting hunks for revert/replace)
#   3. Per-file SHA coverage (files touched by 2+ SHAs are dependency points;
#      files touched by 1 SHA are independent)
#   4. Author-date execution order (a valid topological sort iff no later
#      commit reverts or replaces content from an earlier one — verify this)
#
# This is mechanical. The LLM reads the output and decides:
#   - parallel-investigation islands (zero shared files with all others)
#   - whether author-date order is actually safe or needs a swap
#   - which SHA pairs warrant the most careful conflict resolution
#
# Usage: batch-deps.sh <sha1> <sha2> [<sha3> ...]
#
# Exit codes:
#   0 = analysis complete
#   2 = invocation error or invalid SHA

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <sha1> <sha2> [<sha3> ...]" >&2
  echo "Need at least 2 SHAs for dependency analysis." >&2
  exit 2
fi

for sha in "$@"; do
  if ! git rev-parse --verify "${sha}^{commit}" >/dev/null 2>&1; then
    echo "error: ${sha} is not a valid commit" >&2
    exit 2
  fi
done

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# Build sorted (author date, full sha, short sha, subject) — oldest first
for sha in "$@"; do
  git show -s --format="%aI%x09%H%x09%h%x09%s" "$sha"
done | sort -k1,1 > "$WORK_DIR/sorted"

# Per-SHA file lists; also record (file, short_sha) for overlap analysis
echo "## Per-SHA File Lists (author-date order, oldest first)"
echo
while IFS=$'\t' read -r adate full_sha short_sha subj; do
  echo "### $short_sha — $adate"
  echo "    $subj"
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    echo "    - $f"
    printf '%s\t%s\n' "$f" "$short_sha" >> "$WORK_DIR/file_sha"
  done < <(git diff-tree --no-commit-id --name-only -r "$full_sha")
  echo
done < "$WORK_DIR/sorted"

# SHA pairs sharing files
echo "## SHA Pairs Sharing Files (dependency edges)"
echo
echo "Pairs with overlap need ordering. The earlier SHA (by author date) generally comes first; verify by inspecting hunks for revert/replace patterns."
echo

if [[ -s "$WORK_DIR/file_sha" ]]; then
  PAIRS=$(awk -F'\t' '
    { files[$1] = files[$1] " " $2 }
    END {
      for (f in files) {
        n = split(files[f], shas, " ")
        c = 0
        for (i = 1; i <= n; i++) if (shas[i] != "") arr[++c] = shas[i]
        if (c >= 2) {
          # Sort the SHAs in this group lexicographically for stable pair keys
          for (i = 1; i <= c; i++) {
            for (j = i + 1; j <= c; j++) {
              if (arr[i] > arr[j]) { tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp }
            }
          }
          for (i = 1; i < c; i++) {
            for (j = i + 1; j <= c; j++) {
              key = arr[i] " " arr[j]
              pair_files[key] = pair_files[key] "\t" f
            }
          }
        }
        delete arr
      }
      for (p in pair_files) {
        n = split(pair_files[p], files, "\t")
        printf "%s\t%d\t", p, n - 1
        first = 1
        for (i = 1; i <= n; i++) {
          if (files[i] != "") {
            if (first) { first = 0 } else { printf "," }
            printf "%s", files[i]
          }
        }
        printf "\n"
      }
    }
  ' "$WORK_DIR/file_sha" | sort -k3,3rn -k1,1)

  if [[ -z "$PAIRS" ]]; then
    echo "  (no shared files — all SHAs are independent)"
  else
    while IFS=$'\t' read -r pair count files; do
      printf "  %s — %d shared file(s)\n" "$pair" "$count"
      echo "$files" | tr ',' '\n' | sed 's/^/      /'
    done <<< "$PAIRS"
  fi
fi

echo

# Per-file SHA coverage
echo "## Per-File SHA Coverage"
echo
echo "Files touched by 2+ SHAs are dependency points. Files touched by 1 SHA are safe."
echo

if [[ -s "$WORK_DIR/file_sha" ]]; then
  sort "$WORK_DIR/file_sha" | awk -F'\t' '
    {
      if ($1 != prev) {
        if (prev != "") {
          if (count >= 2) printf "  [×%d] %s : %s\n", count, prev, shas
          else printf "  [×1] %s : %s\n", prev, shas
        }
        prev = $1
        shas = $2
        count = 1
      } else {
        shas = shas " " $2
        count++
      }
    }
    END {
      if (prev != "") {
        if (count >= 2) printf "  [×%d] %s : %s\n", count, prev, shas
        else printf "  [×1] %s : %s\n", prev, shas
      }
    }
  ' | sort -k1,1 -k2,2
fi

echo

# Author-date execution order
echo "## Author-Date Execution Order"
echo
echo "Valid topological sort *if* no later commit reverts or replaces content from an earlier one. Verify by checking the overlap pairs above."
echo
n=0
while IFS=$'\t' read -r adate full_sha short_sha subj; do
  n=$((n + 1))
  printf "  %2d. %s  %s  %s\n" "$n" "$short_sha" "$adate" "$subj"
done < "$WORK_DIR/sorted"

echo
echo "## Independence Check"
echo

if [[ -s "$WORK_DIR/file_sha" ]]; then
  ALL_SHAS=$(awk -F'\t' '{print $3}' "$WORK_DIR/sorted" | sort -u)
  OVERLAPPING_SHAS=$(awk -F'\t' '
    { files[$1] = files[$1] " " $2 }
    END {
      for (f in files) {
        n = split(files[f], shas, " ")
        c = 0
        for (i = 1; i <= n; i++) if (shas[i] != "") arr[++c] = shas[i]
        if (c >= 2) for (i = 1; i <= c; i++) print arr[i]
        delete arr
      }
    }
  ' "$WORK_DIR/file_sha" | sort -u)

  INDEPENDENT=$(comm -23 <(echo "$ALL_SHAS") <(echo "$OVERLAPPING_SHAS") || true)
  if [[ -n "$INDEPENDENT" ]]; then
    echo "Independent SHAs (zero file overlap with any other in this batch — investigate in parallel):"
    echo "$INDEPENDENT" | sed 's/^/  - /'
  else
    echo "No fully-independent SHAs in this batch."
  fi
fi
