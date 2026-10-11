#!/usr/bin/env bash
# batch-preflight.sh — the deterministic batch pre-flight (references/batch.md):
# one TSV row per requested PR or SHA, for CHERRY_PICK.md.
#
# Usage:   batch-preflight.sh <target-branch> <pr-number | #pr | sha>...
# Example: batch-preflight.sh origin/6.1-release 1234 '#1250' 0a1b2c3
# A bare number shorter than 7 digits, or `#N`, is a PR; anything else is a
# commit.
#
# Output columns: status, request, pr, sha, parents, evidence, title
#   ALREADY_APPLIED     — the target's first-parent history carries the PR
#                         number (not since reverted), or a target commit
#                         carries "cherry picked from commit <sha>"
#   NOT_MERGED          — the PR is open or closed without a merge commit
#   NEEDS_INVESTIGATION — merged and not on the target; run investigate/gate
#   PREFLIGHT_BLOCKED   — missing PR, unknown SHA, or gh/git failure
# `parents` is the source commit's parent count: 2 or more means a merge
# commit, picked with `git cherry-pick -x -m 1 <sha>`; 1 means
# `git cherry-pick -x <sha>`. A matching title on the target is advisory only
# (`evidence: title-match (advisory)`); it never makes a row ALREADY_APPLIED.
#
# PR rows need `gh`; SHA rows need only git. Exit codes: 0 success (rows may
# still be blocked), 2 usage error or unknown target.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <target-branch> <pr-number | #pr | sha>..." >&2
  exit 2
fi

target="$1"
shift
if ! git rev-parse --verify --quiet "${target}^{commit}" >/dev/null; then
  echo "error: unknown target branch: $target" >&2
  exit 2
fi

MERGE_PR='^Merge pull request #([0-9]+)'
TRAILING_PR='\(#([0-9]+)\)[[:space:]]*$'
ANY_PR='#([0-9]+)'

pr_number() {
  if [[ $1 =~ $MERGE_PR ]] || [[ $1 =~ $TRAILING_PR ]] || [[ $1 =~ $ANY_PR ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
  fi
}

# PR numbers present in the target's first-parent history. The number is
# taken as pr_number does; a revert of a PR cancels a pick of it, and a revert
# of that revert restores it.
target_prs=$(git log --first-parent --format='%s' "$target" | awk '
  {
    n = ""
    if (match($0, /^Merge pull request #[0-9]+/)) { n = substr($0, RSTART, RLENGTH); sub(/.*#/, "", n) }
    else if (match($0, /\(#[0-9]+\)[ \t]*$/)) { n = substr($0, RSTART, RLENGTH); gsub(/[^0-9]/, "", n) }
    else if (match($0, /#[0-9]+/)) { n = substr($0, RSTART + 1, RLENGTH - 1) }
    if (n == "") next
    if ($0 ~ /^Revert "Revert /) net[n]++
    else if ($0 ~ /^Revert/) net[n]--
    else net[n]++
  }
  END { for (n in net) if (net[n] > 0) print n }' | sort -u)
# Source SHAs a `git cherry-pick -x` already brought onto the target.
picked=$(git log --format='%b' "$target" \
  | grep -oE 'cherry picked from commit [0-9a-f]{7,40}' | awk '{print $5}' | sort -u || true)
target_subjects=$(git log --first-parent --format='%s' "$target")

clean() { tr '\t\n' '  ' <<<"$1" | sed 's/ *$//'; }

row() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "${3:--}" "${4:--}" "${5:--}" "${6:--}" "$(clean "${7:--}")"
}

parents_of() {
  git rev-list --parents -n 1 "$1" | awk '{print NF - 1}'
}

printf 'status\trequest\tpr\tsha\tparents\tevidence\ttitle\n'
for request in "$@"; do
  pr="" sha="" title="" state=""
  number="${request#\#}"
  if [[ $number =~ ^[0-9]+$ ]] && [[ ${#number} -lt 7 || $request == \#* ]]; then
    pr="$number"
    if ! view=$(gh pr view "$pr" --json number,title,state,mergeCommit 2>/dev/null); then
      row PREFLIGHT_BLOCKED "$request" "$pr" "" "" "gh pr view failed" ""
      continue
    fi
    if ! parsed=$(python3 -c '
import json, sys
value = json.loads(sys.stdin.read(), strict=False)
commit = value.get("mergeCommit") or {}
print("\x1f".join([value["state"], (commit.get("oid") or "") if isinstance(commit, dict) else "", value["title"].replace("\t", " ").replace("\n", " ")]))
' <<<"$view" 2>/dev/null); then
      row PREFLIGHT_BLOCKED "$request" "$pr" "" "" "unexpected gh output" ""
      continue
    fi
    # \x1f, not a tab: read collapses empty fields between whitespace separators.
    IFS=$'\x1f' read -r state sha title <<<"$parsed"
    if [[ $state != MERGED || -z $sha ]]; then
      row NOT_MERGED "$request" "$pr" "$sha" "" "state ${state:-unknown}" "$title"
      continue
    fi
  else
    if ! sha=$(git rev-parse --verify --quiet "${request}^{commit}"); then
      row PREFLIGHT_BLOCKED "$request" "" "" "" "unknown commit" ""
      continue
    fi
    title=$(git log -1 --format='%s' "$sha")
    pr=$(pr_number "$title")
  fi
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    row PREFLIGHT_BLOCKED "$request" "$pr" "$sha" "" "merge commit not fetched" "$title"
    continue
  fi
  parents=$(parents_of "$sha")
  marked=""
  while IFS= read -r mark; do
    if [[ -n $mark && $sha == "$mark"* ]]; then
      marked=1
    fi
  done <<<"$picked"
  if [[ -n $pr ]] && grep -qx "$pr" <<<"$target_prs"; then
    row ALREADY_APPLIED "$request" "$pr" "$sha" "$parents" "target first-parent has #$pr" "$title"
  elif [[ -n $marked ]]; then
    row ALREADY_APPLIED "$request" "$pr" "$sha" "$parents" "cherry-pick -x marker" "$title"
  elif [[ -n $title ]] && grep -qxF "$title" <<<"$target_subjects"; then
    row NEEDS_INVESTIGATION "$request" "$pr" "$sha" "$parents" "title-match (advisory)" "$title"
  else
    row NEEDS_INVESTIGATION "$request" "$pr" "$sha" "$parents" "" "$title"
  fi
done
