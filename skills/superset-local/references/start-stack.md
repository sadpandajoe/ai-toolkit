# Start Superset Local

Bring up a local Superset stack and print the frontend URL for browser testing
or Playwright.

## 1. Resource Gate

Read the Docker daemon `Total Memory` and the containers' summed `MemUsage`,
add the per-stack figure from
[check-resources.md](../../workflows/references/check-resources.md), and
proceed when it fits. Otherwise show the math and ask whether to stop a stale
stack or cancel; container count alone is not a stop condition. Skip the gate
when `up.sh` reports the stack already up.

## 2. Start and Wait: `up.sh`

From the Superset worktree root:

```bash
<toolkit-root>/scripts/superset-local/up.sh            # start, wait, print the URL
<toolkit-root>/scripts/superset-local/up.sh --detect   # only print the start command it would use
```

- Returns at once when `superset-light` is `(healthy)` and the node-light port
  answers 200 or 302.
- Otherwise starts the stack with `clo docker up` in a claudette project
  (`$PROJECT` set or a `.claudette` directory), or
  `docker compose -f docker-compose-light.yml up -d` in a plain worktree; exit 1
  when that fails, exit 2 when neither applies.
- Waits up to 5 minutes (`--timeout`, polling every 15 s with `--interval`) for
  the init container's `"Step 4/4 [Complete]"` and then the health check; on
  timeout it prints the last phase and the containers and exits 1, without
  retrying.
- The frontend is the node-light host port (for example
  `0.0.0.0:9002->9000/tcp`), not 8088, which the host does not expose. A
  frontend not answering yet is a warning (webpack may still be compiling).

Do not poll by hand.

## 3. ZSTD Proxy Setting

This applies to older branches and forks only. Current upstream
`superset-frontend/webpack.proxy-config.js` decodes `zstd` itself; check the
branch's copy before suggesting anything. Where the branch's proxy cannot
decode ZSTD, proxied routes such as `/login/` fail with
`ZSTDDecompress is not a function`.

Do not modify application source code by default. `up.sh` warns when
`docker/pythonpath_dev/superset_config_docker_light.py` has no
`COMPRESS_ALGORITHM`; explain the issue and show the one-line patch:

```python
COMPRESS_ALGORITHM = ["gzip"]
```

Apply it only after an explicit `--apply-proxy-fix` request: show
`git status --short` before, and the exact diff after, so the user can tell the
environment workaround from product changes. A running stack needs a restart
to pick it up.

## 4. Output

```
## Superset Local Ready

- Backend: healthy (inside Docker)
- Frontend: http://localhost:$PORT (HTTP $STATUS_CODE)
- Playwright: PLAYWRIGHT_BASE_URL=http://localhost:$PORT
```
