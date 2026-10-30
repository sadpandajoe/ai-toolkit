---
name: superset-local
description: Start a local Superset stack and find its frontend URL, check Docker capacity first, and run Superset's Playwright E2E specs against it. Use for Superset or Preset local stack startup, stale-container checks, the ZSTD proxy issue, and local Playwright runs. Do NOT use for production, staging, generic Docker work, or unrelated web apps.
---

# Superset Local

## Capacity first

- Docker Desktop's memory cap (`Total Memory` in `docker info`) bounds all
  containers together, independent of host RAM. A Superset-class stack takes
  about 5 GB.
- Headroom is the cap minus the containers' summed `MemUsage`
  (`docker stats --no-stream`). Over 6 GB with over 4 GB host memory free:
  go. 3–6 GB: marginal, offer to stop a stale stack first. Under 3 GB: no-go
  until a stack stops or the cap rises. Running out is an OOM kill, not a
  slowdown, so warn at 70% of the cap; container count alone is not a reason
  to stop.
- A container is stale when it has been up over 24 hours or is named for
  another branch (`fix-*`, `feat-*`, `bug-*`). Stop only the containers the
  user names, with the exact `docker stop <names>`.
- Never change Docker Desktop settings programmatically; suggest Settings →
  Resources → Memory.
- A git worktree shares `.git` but not dependencies, build outputs or `.env`
  files; install or copy them before tests or builds there.

Skip the capacity check when `up.sh` reports the stack already up.

## Start: `up.sh`

From the Superset worktree root:

```bash
<skill-dir>/scripts/up.sh            # start, wait, print the URL
<skill-dir>/scripts/up.sh --detect   # only print the start command it would use
```

- Returns at once when `superset-light` is `(healthy)` and the node-light port
  answers 200 or 302.
- Otherwise starts with `clo docker up` in a claudette project (`$PROJECT` set
  or a `.claudette` directory), or `docker compose -f docker-compose-light.yml
  up -d` in a plain worktree. Exit 1 when that fails or times out, exit 2 when
  neither applies.
- Waits up to 5 minutes (`--timeout`, polling every 15 s with `--interval`) for
  the init container's `"Step 4/4 [Complete]"` and then the health check. Do
  not poll by hand, and do not retry a timeout automatically.
- The frontend is the node-light host port (for example
  `0.0.0.0:9002->9000/tcp`), not 8088, which the host does not expose. A
  frontend not answering yet is a warning: webpack may still be compiling.

## ZSTD proxy (older branches only)

Current upstream `superset-frontend/webpack.proxy-config.js` decodes `zstd`
itself; check the branch's copy first. Where it cannot, proxied routes such as
`/login/` fail with `ZSTDDecompress is not a function`. `up.sh` warns when
`docker/pythonpath_dev/superset_config_docker_light.py` has no
`COMPRESS_ALGORITHM`. The fix is one line, `COMPRESS_ALGORITHM = ["gzip"]`,
applied only when the user asks for it: show `git status --short` before and
the exact diff after, so the workaround is not mistaken for a product change.
A running stack needs a restart to pick it up.

## Playwright E2E

```bash
cd superset-frontend
PLAYWRIGHT_BASE_URL=http://localhost:$PORT npx playwright test [<spec>] --reporter=list
```

Keep `playwright.config`'s workers and retries. Report failures rather than
retrying them, and point to `npx playwright show-trace <trace.zip>` when
traces exist.

| Symptom | Cause and fix |
|---------|---------------|
| Auth timeout on `localhost:8088` | Wrong base URL: use the node-light host port |
| `ZSTDDecompress is not a function` | ZSTD proxy, above |
| Global setup fails on the first run, then works | Transient first-run auth timeout: retry the run once |
| Tab count assertions off | Stale tab state: tests should use relative counts |
| `browserType.launch` fails | `npx playwright install chromium` |
