#!/usr/bin/env bash
# up.sh — start a local Superset stack and print the Playwright base URL
# (skills/superset-local/references/start-stack.md).
#
# Usage: up.sh [--detect] [--timeout <seconds>] [--interval <seconds>]
#   --detect    print the start command this worktree would use, then exit
#
# Run from the Superset worktree root. A claudette project ($PROJECT set, or a
# .claudette directory) starts with `clo docker up`; a plain worktree with
# `docker compose -f docker-compose-light.yml up -d`. The script then waits
# (default 300 s, polling every 15 s) for the init container's
# "Step 4/4 [Complete]" and a healthy superset-light container, finds the
# node-light host port, checks it answers 200 or 302, and prints
# PLAYWRIGHT_BASE_URL for that port (not 8088, which the host does not
# expose). It never edits application source: a missing ZSTD proxy setting is
# reported, and the fix stays the user's explicit choice.
#
# Exit codes: 0 ready, 1 the stack failed or timed out, 2 usage error or no
# stack definition in this directory.

set -euo pipefail

timeout=300
interval=15
detect=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --detect) detect=1 ;;
    --timeout) timeout="${2:?--timeout needs seconds}"; shift ;;
    --interval) interval="${2:?--interval needs seconds}"; shift ;;
    -h | --help) sed -n '4,5p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "up.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
for value in "$timeout" "$interval"; do
  [[ $value =~ ^[0-9]+$ ]] || { echo "up.sh: --timeout and --interval take whole seconds" >&2; exit 2; }
done

if [[ -n "${PROJECT:-}" || -d .claudette ]]; then
  start=(clo docker up)
elif [[ -f docker-compose-light.yml ]]; then
  start=(docker compose -f docker-compose-light.yml up -d)
else
  echo "up.sh: no claudette project and no docker-compose-light.yml here; run from a Superset worktree" >&2
  exit 2
fi
if [[ $detect -eq 1 ]]; then
  printf '%s\n' "${start[*]}"
  exit 0
fi

config=docker/pythonpath_dev/superset_config_docker_light.py
if [[ -f $config ]] && ! grep -q 'COMPRESS_ALGORITHM' "$config"; then
  echo "warning: $config has no COMPRESS_ALGORITHM; proxied routes may fail with ZSTDDecompress errors." >&2
  echo "         The one-line fix (COMPRESS_ALGORITHM = [\"gzip\"]) is applied only on an explicit request." >&2
fi

containers() { docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'; }

node_port() {
  containers | awk -F'\t' '$1 ~ /node-light/ {print $3}' \
    | grep -oE '[0-9.:]+:[0-9]+->9000' | head -n 1 | sed -E 's/.*:([0-9]+)->9000/\1/'
}

frontend_status() {
  curl -s -o /dev/null -w '%{http_code}' "http://localhost:$1/" || true
}

healthy() { containers | awk -F'\t' '$1 ~ /superset-light/ && $2 ~ /\(healthy\)/' | grep -q .; }

report() {
  printf '## Superset Local Ready\n\n'
  printf -- '- Backend: healthy (inside Docker)\n'
  printf -- '- Frontend: http://localhost:%s (HTTP %s)\n' "$1" "$2"
  printf -- '- Playwright: PLAYWRIGHT_BASE_URL=http://localhost:%s\n' "$1"
}

port=$(node_port || true)
if healthy && [[ -n $port ]]; then
  code=$(frontend_status "$port")
  if [[ $code == 200 || $code == 302 ]]; then
    report "$port" "$code"
    exit 0
  fi
fi

echo "Starting: ${start[*]}" >&2
if ! "${start[@]}"; then
  echo "up.sh: '${start[*]}' failed; check that Docker is running" >&2
  exit 1
fi

deadline=$((SECONDS + timeout))
phase=init
while :; do
  if [[ $phase == init ]]; then
    init=$(docker ps -a --format '{{.Names}}' | grep -E 'init' | head -n 1 || true)
    if [[ -n $init ]] && docker logs "$init" 2>&1 | grep -q 'Step 4/4 \[Complete\]'; then
      echo "Init complete. Waiting for health check..." >&2
      phase=health
      continue
    fi
  elif healthy; then
    echo "Superset is healthy." >&2
    break
  fi
  if ((SECONDS >= deadline)); then
    echo "up.sh: not ready after ${timeout}s (last phase: $phase)" >&2
    containers >&2 || true
    exit 1
  fi
  sleep "$interval"
done

port=$(node_port || true)
if [[ -z $port ]]; then
  echo "up.sh: no node-light container publishing port 9000" >&2
  exit 1
fi
code=000
# Probe for up to 60 s. bash 3.2 (macOS) evaluates both arms of `?:`, so a
# division by a zero interval must not appear in the expression at all.
tries=1
if ((interval > 0)); then
  tries=$(((60 + interval - 1) / interval))
fi
for ((try = 0; try < tries; try++)); do
  code=$(frontend_status "$port")
  [[ $code == 200 || $code == 302 ]] && break
  sleep "$interval"
done
if [[ $code != 200 && $code != 302 ]]; then
  echo "warning: the frontend on port $port answered HTTP $code; webpack may still be compiling" >&2
fi
report "$port" "$code"
