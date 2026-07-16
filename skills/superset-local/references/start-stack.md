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

### 1. Check Already Running

Before doing anything, check if the project's stack is already up and healthy:

```bash
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

If a container matching the current project name shows `(healthy)` AND the frontend port responds (curl returns 200 or 302), skip to **Step 7 (Output)** — the stack is already ready.

### 2. Resource Gate

Read the Docker daemon `Total Memory` and aggregate current `MemUsage`. Add the
4–6 GB Superset estimate and proceed when it fits. If it risks over-capacity,
show the math and ask whether to stop a stale stack or cancel. Container count
alone is not a stop condition.

### 3. Detect ZSTD Proxy Configuration

Check `docker/pythonpath_dev/superset_config_docker_light.py` for `COMPRESS_ALGORITHM`:

```bash
grep -q 'COMPRESS_ALGORITHM' docker/pythonpath_dev/superset_config_docker_light.py
```

Do not modify application source code by default. If the line is missing,
explain the known local-proxy issue and show the proposed one-line patch:

```python
COMPRESS_ALGORITHM = ["gzip"]
```

Apply this source change only after an explicit `--apply-proxy-fix` request.
Before applying it, show `git status --short`; afterward, show the exact diff so
the user can distinguish the environment workaround from product changes.

Why: webpack's dev server proxy cannot decompress ZSTD responses from Flask. Without this, requests to `/login/` and other proxied routes fail with `ZSTDDecompress is not a function`. If the stack was already running, it needs a restart for this to take effect.

If the line already exists, skip this step silently.

### 4. Detect Environment and Start Stack

Detect whether this is a claudette-managed project:

```bash
# Check for claudette environment
echo "$PROJECT"
ls .claudette 2>/dev/null
```

- **Claudette project** (`$PROJECT` is set or `.claudette` exists): use `clo docker up`
- **Plain worktree**: use `docker compose -f docker-compose-light.yml up -d`

Run the appropriate command. This starts the database, init container, node dev server, and (after init completes) the app server.

If the start command fails (non-zero exit, Docker daemon not running, compose file not found), report the error and stop — don't proceed to health polling.

### 5. Wait for Init and Health

Poll in a loop (max 5 minutes, check every 15 seconds). Check Docker resource usage per `rules/resource-management.md` before entering the loop — if the Docker VM is already under memory pressure, warn the user.

1. **Init phase**: Check init container logs for `"Step 4/4 [Complete]"` — this means migrations, permissions, and example data are loaded
2. **Health phase**: Check `docker ps` for the `superset-light` container showing `(healthy)`

Report progress at each phase transition:
- "Init: loading examples (step 4/4)..."
- "Init complete. Waiting for health check..."
- "Superset is healthy."

If 5 minutes pass without reaching healthy, report the last known state and stop — don't retry endlessly.

### 6. Frontend Check

Detect the frontend port from `docker ps` port mapping (look for the node container's host port, e.g., `0.0.0.0:9002->9000/tcp`).

```bash
docker ps --format "{{.Names}}\t{{.Ports}}" | grep "node-light"
```

Curl the detected port until it returns HTTP 200 or 302 (redirect to login is expected):

```bash
curl -sf -o /dev/null -w "%{http_code}" http://localhost:$PORT/
```

If the frontend doesn't respond within 60 seconds after the backend is healthy, report it as a warning — the webpack dev server may still be compiling.

### 7. Output

Print a clear summary:

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
