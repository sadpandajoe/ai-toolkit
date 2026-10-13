#!/usr/bin/env bash
# unblock-measure.sh — measure the unblock candidates for a blocked cherry
# (references/unblock-discovery.md): one TSV row per PR, then a chain row.
#
# Usage:   unblock-measure.sh <owner/repo> <pr-number | #pr>...
# Example: unblock-measure.sh octo/widgets 1234 '#1250'
#
# Output columns: pr, files, added, removed, migration, rating, title
#   migration  yes when a changed file is under migrations/versions/; unknown
#              when gh listed fewer files than the PR changed and none matched
#   rating     risky when migration is yes; heavy when more than 15 files
#              changed or migration is unknown; easy otherwise
# A PR that gh cannot read gets rating `unmeasured`. The last row, `chain`,
# sums the measured rows and takes the worst rating (easy < heavy < risky);
# any unmeasured row makes the chain `unmeasured`, so a missing measurement
# never reads as easy. A reviewer may raise a rating (shared infrastructure,
# auth, RLS), never lower it.
#
# Needs gh. Exit codes: 0 success (rows may be unmeasured), 2 usage error.

set -euo pipefail

usage() {
  echo "usage: $0 <owner/repo> <pr-number | #pr>..." >&2
  exit 2
}

[[ $# -ge 2 && $1 == ?*/?* ]] || usage
repo="$1"
shift
for request in "$@"; do
  [[ ${request#\#} =~ ^[0-9]+$ ]] || usage
done

MEASURE='
import json, sys
value = json.loads(sys.stdin.read(), strict=False)
files = value.get("files") or []
changed = int(value.get("changedFiles") or len(files))
paths = [str(item.get("path", "")) for item in files]
if any("migrations/versions/" in path for path in paths):
    migration = "yes"
elif len(paths) < changed:
    migration = "unknown"
else:
    migration = "no"
if migration == "yes":
    rating = "risky"
elif changed > 15 or migration == "unknown":
    rating = "heavy"
else:
    rating = "easy"
title = " ".join(str(value.get("title") or "-").split()) or "-"
print("\t".join([str(changed), str(int(value.get("additions") or 0)),
                 str(int(value.get("deletions") or 0)), migration, rating, title]))
'

total_files=0 total_added=0 total_removed=0 rank=0 migrations=no unmeasured=0
printf 'pr\tfiles\tadded\tremoved\tmigration\trating\ttitle\n'
for request in "$@"; do
  pr="${request#\#}"
  if ! view=$(gh pr view "$pr" --repo "$repo" --json number,title,changedFiles,additions,deletions,files 2>/dev/null) \
    || ! measured=$(python3 -c "$MEASURE" <<<"$view" 2>/dev/null); then
    printf '#%s\t-\t-\t-\t-\tunmeasured\tgh pr view failed\n' "$pr"
    unmeasured=1
    continue
  fi
  IFS=$'\t' read -r files added removed migration rating title <<<"$measured"
  printf '#%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$pr" "$files" "$added" "$removed" "$migration" "$rating" "$title"
  total_files=$((total_files + files))
  total_added=$((total_added + added))
  total_removed=$((total_removed + removed))
  case "$rating" in
    risky) rank=2 ;;
    heavy) [[ $rank -ge 1 ]] || rank=1 ;;
  esac
  if [[ $migration == yes ]]; then
    migrations=yes
  elif [[ $migration == unknown && $migrations == no ]]; then
    migrations=unknown
  fi
done
case "$rank" in
  2) chain=risky ;;
  1) chain=heavy ;;
  *) chain=easy ;;
esac
[[ $unmeasured -eq 0 ]] || chain=unmeasured
printf 'chain\t%s\t%s\t%s\t%s\t%s\t%s PRs\n' "$total_files" "$total_added" "$total_removed" "$migrations" "$chain" "$#"
