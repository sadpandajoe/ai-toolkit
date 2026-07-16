#!/usr/bin/env bash
# release-audit.sh — list PR-level changes on a source branch that have not
# reached a release branch, using FIRST-PARENT merge history only.
#
# Usage:   release-audit.sh <release-branch> [<source-branch>]
# Example: release-audit.sh origin/6.1-release origin/master
#
# Output: TSV — status, short sha, PR number, subject — one row per
# first-parent commit on the source side since the merge-base.
#   MISSING                — no PR-number match on target, no -x marker
#   PRESENT-BY-PR          — same PR number appears in target's first-parent log
#   PRESENT-BY-CHERRY-MARK — a commit on target carries "cherry picked from
#                            commit <this sha>"
#
# MISSING rows are candidates, not decisions: verify each with
# `gh pr view <n>` before queuing (see references/release-audit.md).

set -euo pipefail

target="${1:?usage: release-audit.sh <release-branch> [<source-branch>]}"
source_branch="${2:-$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/master)}"

mb=$(git merge-base "$source_branch" "$target")

# PR numbers already represented in the target's own first-parent history
# (its merges/squashes since divergence, including prior cherry-picks that
# kept the "(#N)" suffix).
target_prs=$(git log --first-parent --format='%s' "$mb..$target" \
  | grep -oE '#[0-9]+' | tr -d '#' | sort -u || true)

# Source SHAs already applied to target via `git cherry-pick -x` markers —
# the only exact already-applied evidence (PR/title matches are advisory).
picked_shas=$(git log --format='%b' "$mb..$target" \
  | grep -oE 'cherry picked from commit [0-9a-f]{7,40}' | awk '{print $5}' | sort -u || true)

printf 'status\tsha\tpr\tsubject\n'
git log --first-parent --reverse --format='%H%x09%s' "$mb..$source_branch" \
| while IFS=$'\t' read -r sha subject; do
    pr=$(grep -oE '#[0-9]+' <<<"$subject" | head -1 | tr -d '#' || true)
    status="MISSING"
    if [ -n "$pr" ] && grep -qx "$pr" <<<"$target_prs"; then
      status="PRESENT-BY-PR"
    elif [ -n "$picked_shas" ] && grep -qx "$sha" <<<"$picked_shas"; then
      status="PRESENT-BY-CHERRY-MARK"
    fi
    printf '%s\t%s\t%s\t%s\n' "$status" "${sha:0:10}" "${pr:--}" "$subject"
  done
