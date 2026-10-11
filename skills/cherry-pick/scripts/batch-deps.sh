#!/usr/bin/env bash
#
# batch-deps.sh — file-overlap analysis for cherry-pick batches.
#
# Given a list of source SHAs (must be reachable in the local git repo), emits
# the mechanical signals needed to build a real dependency-aware execution order:
#
#   1. Per-SHA file lists (execution order, earliest first). A merge commit
#      lists the files it changes against its first parent.
#   2. SHA pairs that share files (dependency edges; the earlier one should
#      generally come first, but verify by inspecting hunks for revert/replace)
#   3. Per-file SHA coverage (files touched by 2+ SHAs are dependency points;
#      files touched by 1 SHA are independent)
#   4. Execution order: each SHA's position in
#      `git rev-list --first-parent --reverse <merge-base>..<source>`, the order
#      the changes landed on the source branch (a SHA inside a merged branch
#      takes the position of the merge that brought it in). Without --source,
#      commit-time order. Either is a valid topological sort iff no later
#      commit reverts or replaces content from an earlier one — verify this.
#
# This is mechanical. The LLM reads the output and decides:
#   - parallel-investigation islands (zero shared files with all others)
#   - whether the execution order is actually safe or needs a swap
#   - which SHA pairs warrant the most careful conflict resolution
#
# Usage: batch-deps.sh [--source <ref> [--target <ref>]] <sha1> <sha2> [<sha3> ...]
#   --source  the branch the SHAs come from (for example origin/master)
#   --target  the branch they go to (default: HEAD); the merge-base of the two
#             bounds the first-parent walk
#
# Exit codes:
#   0 = analysis complete
#   2 = invocation error or invalid SHA

set -euo pipefail

SOURCE_REF=""
TARGET_REF="HEAD"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_REF="${2:?--source needs a ref}"; shift 2 ;;
    --target) TARGET_REF="${2:?--target needs a ref}"; shift 2 ;;
    --) shift; break ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done

if [[ $# -lt 2 ]]; then
  echo "usage: $0 [--source <ref> [--target <ref>]] <sha1> <sha2> [<sha3> ...]" >&2
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

if [[ -n "$SOURCE_REF" ]]; then
  if ! BASE=$(git merge-base "$TARGET_REF" "$SOURCE_REF" 2>/dev/null); then
    echo "error: no merge-base between $TARGET_REF and $SOURCE_REF" >&2
    exit 2
  fi
  ORDER_LABEL="first-parent position on $SOURCE_REF"
  git rev-list --first-parent --reverse "$BASE..$SOURCE_REF" | awk '{ print $1 "\t" NR }' > "$WORK_DIR/first_parent"
else
  ORDER_LABEL="commit time; pass --source for first-parent order"
fi

# The position of a SHA on the source branch's first-parent line: its own,
# or that of the first first-parent commit that contains it (the merge that
# brought it in). Unknown SHAs sort after every known one.
position() {
  local sha=$1 pos container
  pos=$(awk -F'\t' -v sha="$sha" '$1 == sha { print $2; exit }' "$WORK_DIR/first_parent")
  if [[ -z "$pos" ]]; then
    while IFS= read -r container; do
      pos=$(awk -F'\t' -v sha="$container" '$1 == sha { print $2; exit }' "$WORK_DIR/first_parent")
      [[ -n "$pos" ]] && break
    done < <(git rev-list --reverse --ancestry-path "$sha..$SOURCE_REF" 2>/dev/null)
  fi
  echo "${pos:-999999999}"
}

# Build sorted (order key, full sha, short sha, subject), earliest first
for sha in "$@"; do
  full=$(git rev-parse --verify "${sha}^{commit}")
  if [[ -n "$SOURCE_REF" ]]; then
    key=$(position "$full")
  else
    key=$(git show -s --format=%ct "$full")
  fi
  printf '%s\t%s\n' "$key" "$(git show -s --format="%H%x09%h%x09%s" "$full")"
done | sort -t $'\t' -k1,1n -k2,2 > "$WORK_DIR/sorted"

# The files a commit changes; a merge against its first parent.
changed_files() {
  if git rev-parse --verify --quiet "$1^1" >/dev/null; then
    git diff --name-only "$1^1" "$1"
  else
    git diff-tree --root --no-commit-id --name-only -r "$1"
  fi
}

# Per-SHA file lists; also record (file, short_sha) for overlap analysis
echo "## Per-SHA File Lists (execution order: $ORDER_LABEL)"
echo
while IFS=$'\t' read -r key full_sha short_sha subj; do
  echo "### $short_sha"
  echo "    $subj"
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    echo "    - $f"
    printf '%s\t%s\n' "$f" "$short_sha" >> "$WORK_DIR/file_sha"
  done < <(changed_files "$full_sha")
  echo
done < "$WORK_DIR/sorted"

# SHA pairs sharing files
echo "## SHA Pairs Sharing Files (dependency edges)"
echo
echo "Pairs with overlap need ordering. The SHA earlier in the execution order generally comes first; verify by inspecting hunks for revert/replace patterns."
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

# Execution order
echo "## Execution Order ($ORDER_LABEL)"
echo
echo "Valid topological sort *if* no later commit reverts or replaces content from an earlier one. Verify by checking the overlap pairs above."
echo
n=0
while IFS=$'\t' read -r key full_sha short_sha subj; do
  n=$((n + 1))
  printf "  %2d. %s  %s\n" "$n" "$short_sha" "$subj"
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
