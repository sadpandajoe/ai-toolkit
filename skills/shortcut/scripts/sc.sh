#!/usr/bin/env bash
# sc.sh — Shortcut REST calls with the session gotchas handled
# (skills/shortcut/references/fetch.md).
#
# Usage:
#   sc.sh get <path>                 GET  /api/v3<path>
#   sc.sh post <path> <json|@file>   POST /api/v3<path> with a JSON body
#   sc.sh put <path> <json|@file>    PUT  /api/v3<path> with a JSON body
#   sc.sh upload [--story <id>] <file>...
#                                    POST /api/v3/files (multipart: file0, file1, ...);
#                                    --story also attaches them to that story
#   sc.sh search <query>             GET  /api/v3/search/stories, following `next`
#
# Every call sends `Shortcut-Token: $SHORTCUT_API_TOKEN` (the token is never
# printed), uses `curl --fail-with-body` so an HTTP error is an error, and
# retries once on a failure or an `organization2_missing` body. Output is JSON
# re-serialised from `json.loads(strict=False)`, so control characters in
# descriptions and comments no longer break `jq`. `search` prints one array of
# every page's `data`. SHORTCUT_API_BASE overrides https://api.app.shortcut.com.
#
# Exit codes: 0 success, 1 the call failed after its retry, 2 usage error.

set -euo pipefail

BASE="${SHORTCUT_API_BASE:-https://api.app.shortcut.com}"
API="$BASE/api/v3"

usage() {
  sed -n '4,12p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
if [[ -z "${SHORTCUT_API_TOKEN:-}" ]]; then
  echo "sc.sh: SHORTCUT_API_TOKEN is not set" >&2
  exit 2
fi

# The parsed body, compact and safe for jq; a non-JSON body is printed as is.
normalise() {
  python3 -c '
import json, sys
text = sys.stdin.read()
try:
    value = json.loads(text, strict=False)
except ValueError:
    sys.stdout.write(text)
else:
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
'
}

# call <curl arguments...>: one retry on a curl failure or organization2_missing.
call() {
  local result="" attempt
  for attempt in 1 2; do
    if result=$(curl -sS --fail-with-body \
        -H "Shortcut-Token: $SHORTCUT_API_TOKEN" "$@") \
      && [[ $result != *organization2_missing* ]]; then
      printf '%s' "$result" | normalise
      return 0
    fi
  done
  printf 'sc.sh: Shortcut API failed after retry: %s\n' "$result" >&2
  return 1
}

body() {
  local value="$1"
  if [[ $value == @* ]]; then
    [[ -f ${value#@} ]] || { echo "sc.sh: no such body file: ${value#@}" >&2; exit 2; }
  fi
  printf '%s' "$value"
}

command="$1"
shift
case "$command" in
  get)
    [[ $# -eq 1 ]] || usage
    call "$API$1"
    ;;
  post | put)
    [[ $# -eq 2 ]] || usage
    data=$(body "$2")
    call -X "$(tr '[:lower:]' '[:upper:]' <<<"$command")" -H 'Content-Type: application/json' \
      --data-binary "$data" "$API$1"
    ;;
  upload)
    parts=()
    if [[ ${1:-} == --story ]]; then
      [[ ${2:-} =~ ^[0-9]+$ ]] || usage
      parts+=(-F "story_id=$2")
      shift 2
    fi
    [[ $# -ge 1 ]] || usage
    index=0
    for file in "$@"; do
      [[ -f $file ]] || { echo "sc.sh: no such file: $file" >&2; exit 2; }
      parts+=(-F "file$index=@$file")
      index=$((index + 1))
    done
    call -X POST "${parts[@]}" "$API/files"
    ;;
  search)
    [[ $# -eq 1 ]] || usage
    query=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1")
    url="$API/search/stories?query=$query&page_size=25"
    pages=$(mktemp)
    trap 'rm -f "$pages"' EXIT
    while [[ -n $url ]]; do
      page=$(call "$url")
      printf '%s\n' "$page" >>"$pages"
      next=$(printf '%s' "$page" | python3 -c '
import json, sys
value = json.loads(sys.stdin.read(), strict=False)
print((value.get("next") or "") if isinstance(value, dict) else "")
')
      url="${next:+$BASE$next}"
    done
    python3 - "$pages" <<'PY'
import json, sys
stories = []
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        if line.strip():
            page = json.loads(line, strict=False)
            stories.extend((page.get("data") or []) if isinstance(page, dict) else [])
print(json.dumps(stories, ensure_ascii=False))
PY
    ;;
  *)
    usage
    ;;
esac
