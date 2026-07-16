# Preflight Rules

Read this when a workflow is preparing a local app, Docker stack, or git worktree.

## Docker Container Management

Before starting any Docker containers:
1. Run `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"` to inspect running containers.
2. **Stale check** — flag any container whose `STATUS` shows `Up` for more than 24 hours, or whose name contains a feature/branch prefix that doesn't match the current working branch (e.g., `fix-foo-*`, `feat-bar-*`). List the stale ones with their age and ask the user whether to stop them before starting new work. Do not stop containers without confirmation.
3. **Capacity check** — compare aggregate container memory usage plus the new
   stack estimate with the Docker daemon ceiling. Proceed when it fits; ask
   before starting only when the estimate risks over-capacity. Container count
   alone is not a stop condition.

### Capacity math

Run `docker info | grep -E "CPUs|Total Memory"` once per session to know the daemon's ceiling. The Total Memory value caps the *aggregate* across all containers, regardless of host RAM.

- Each Superset stack uses 4–6 GB.
- Lightweight services (redis, postgres, single web service) typically use < 200 MB each.
- If aggregate `MemUsage` (from `docker stats --no-stream`) is approaching 70 % of the daemon Total Memory, warn the user before starting another stack — running out of Docker memory triggers OOM kills, not gradual slowdown.

If the daemon cap looks too low for the user's workflow (e.g., < 12 GB on a host with 32 GB+ of RAM), mention raising it in Docker Desktop → Settings → Resources → Memory. Do not modify Docker Desktop settings programmatically.

## Worktree Management

When working in git worktrees, remember that worktrees share `.git` but not:
- `node_modules/` or equivalent dependency folders
- build outputs such as `dist/`, `.next/`, or `__pycache__/`
- `.env` files

Before running tests or builds in a worktree:
1. Check whether dependencies exist; install if needed.
2. Check whether build outputs are required; rebuild if needed.
3. Copy `.env` or `.env.local` from the main worktree if needed.

Worktrees created by agents may be auto-cleaned if no changes were made. If changes exist, return the worktree path and branch for merge or manual cleanup.
