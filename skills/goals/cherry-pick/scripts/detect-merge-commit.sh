#!/usr/bin/env bash
#
# detect-merge-commit.sh — report whether a commit is a merge commit.
#
# Usage: detect-merge-commit.sh <commit-sha>
#
# Output: "single" for 1-parent commits, "merge" for 2+ parents.
# Exit codes: 0 success, 2 invocation error.
#
# Cherry-pick hint:
#   single → git cherry-pick -x <commit>
#   merge  → git cherry-pick -x -m 1 <commit>

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <commit-sha>" >&2
  exit 2
fi

COMMIT="$1"

if ! git rev-parse --verify "${COMMIT}^{commit}" >/dev/null 2>&1; then
  echo "error: ${COMMIT} is not a valid commit" >&2
  exit 2
fi

PARENT_COUNT=$(git rev-list --parents -1 "$COMMIT" | awk '{print NF - 1}')

if [[ "$PARENT_COUNT" -ge 2 ]]; then
  echo "merge"
  echo "parents: $PARENT_COUNT"
  echo "use: git cherry-pick -x -m 1 $COMMIT"
else
  echo "single"
  echo "parents: 1"
  echo "use: git cherry-pick -x $COMMIT"
fi
