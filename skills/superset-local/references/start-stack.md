---
tier: Standard
---

# Run Superset Local

Spin up a local Superset development stack and ensure it's ready for browser testing or Playwright E2E tests. Handles Docker resource management, known proxy issues, health polling, and port detection.

## When to Use

- Before running Playwright E2E tests locally
- When the user asks to "spin up", "start", "bring up" Superset locally
- When a healthy Superset container is needed but none is running
- Called by other skills/commands that need a running local environment

## Steps

### 1. Resource Gate

Read the Docker daemon `Total Memory` and aggregate current `MemUsage`. Add the
4–6 GB Superset estimate and proceed when it fits. If it risks over-capacity,
show the math and ask whether to stop a stale stack or cancel. Container count
alone is not a stop condition. Skip the gate when the stack is already up
(`up.sh` reports it ready without starting anything).

### 2. Start and Wait: `up.sh`

From the Superset worktree root:

```bash
<toolkit-root>/scripts/superset-local/up.sh            # start, wait, print the URL
<toolkit-root>/scripts/superset-local/up.sh --detect   # only print the start command it would use
```

The script:

- returns at once when a `superset-light` container is `(healthy)` and the node-light port answers 200 or 302;
- otherwise starts the stack with `clo docker up` in a claudette project (`$PROJECT` set or a `.claudette` directory) or `docker compose -f docker-compose-light.yml up -d` in a plain worktree, and stops with the error when that fails (exit 1) or neither applies (exit 2);
- waits up to 5 minutes (`--timeout`, polling every 15 s, `--interval`) for the init container's `"Step 4/4 [Complete]"` (migrations, permissions and examples loaded) and then the `superset-light` health check, reporting each transition; on timeout it prints the last phase and the container list and exits 1, without retrying;
- finds the node-light host port (for example `0.0.0.0:9002->9000/tcp`) and checks it for 60 seconds; a frontend that is not answering yet is a warning (webpack may still be compiling), not a failure.

Do not poll by hand. If the Docker VM is already under memory pressure (`rules/resource-management.md`), warn the user before running it.

### 3. ZSTD Proxy Configuration

`up.sh` warns when `docker/pythonpath_dev/superset_config_docker_light.py` has
no `COMPRESS_ALGORITHM`. Do not modify application source code by default. If
the line is missing, explain the known local-proxy issue and show the proposed
one-line patch:

```python
COMPRESS_ALGORITHM = ["gzip"]
```

Apply this source change only after an explicit `--apply-proxy-fix` request.
Before applying it, show `git status --short`; afterward, show the exact diff so
the user can distinguish the environment workaround from product changes.

Why: webpack's dev server proxy cannot decompress ZSTD responses from Flask. Without this, requests to `/login/` and other proxied routes fail with `ZSTDDecompress is not a function`. If the stack was already running, it needs a restart for this to take effect.

### 4. Output

`up.sh` prints:

```
## Superset Local Ready

- Backend: healthy (inside Docker)
- Frontend: http://localhost:$PORT (HTTP $STATUS_CODE)
- Playwright: PLAYWRIGHT_BASE_URL=http://localhost:$PORT
```

The `PLAYWRIGHT_BASE_URL` line is the key output — other skills and the user need this to run Playwright tests against the local dev server (not the default `localhost:8088` which isn't exposed on the host).

## What This Skill Does NOT Do

- Run tests (that's the caller's job)
- Modify application source code unless `--apply-proxy-fix` was explicitly requested
- Install dependencies or build frontend assets
- Make architectural decisions
