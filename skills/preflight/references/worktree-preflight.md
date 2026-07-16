# Worktree Preflight

Run this once when entering a newly-created git worktree, before any build, test, or agent work begins. Worktrees share `.git` with the main checkout but **not** dependencies, build outputs, or env files — so a fresh worktree often looks ready but fails the moment you run anything.

See `rules/resource-management.md` for the underlying rationale.

## When to Run

- Immediately after the `isolated_worktree` capability creates or enters a worktree
- Skip if the worktree was already prepared earlier in the same session

## Checks

Run these in order. Stop and report if any check can't be resolved automatically.

### 1. Locate the main worktree

```bash
MAIN_WT=$(git worktree list --porcelain | awk '/^worktree / {print $2; exit}')
CUR_WT=$(git rev-parse --show-toplevel)
```

If `MAIN_WT` equals `CUR_WT`, you are in the main checkout — skip the rest.

### 2. Dependencies

Detect the stack and verify installed deps. Install only if missing; do not reinstall on version mismatch without asking.

| If present | Check | Install command |
|---|---|---|
| `package.json` | `node_modules/` exists and is non-empty | `npm install` (or `yarn` / `pnpm install` matching lockfile) |
| `requirements.txt` | active venv has packages | `pip install -r requirements.txt` |
| `pyproject.toml` | `.venv/` or poetry env exists | `poetry install` or `uv sync` matching project config |
| `Gemfile` | `vendor/bundle` or system bundle current | `bundle install` |
| `go.mod` | module cache populated | `go mod download` |

### 3. Env files

For each of `.env`, `.env.local`, `.env.development` present in `$MAIN_WT` but missing in `$CUR_WT`:

```bash
cp "$MAIN_WT/.env.local" "$CUR_WT/.env.local"   # adjust filename per match
```

Do not copy files containing `production` in the name without asking.

### 4. Build artifacts (only if the task needs them)

Rebuild only when the task actually requires a working app or bundle. Skip for pure code-reading or unit-test tasks.

- Frontend bundle: run the project's build script (check `package.json` scripts for `build` / `dev`)
- Python compiled assets: usually regenerated automatically — skip unless the task fails without them

### 5. Services

Do not auto-start Docker, dev servers, or databases. Surface what's needed and let the user decide — see Docker container rules in `rules/resource-management.md`.

## Output

```markdown
## Worktree Preflight

- Worktree: <path>
- Main checkout: <path>
- Dependencies: <installed / already present / skipped — reason>
- Env files: <copied: .env.local / none needed / blocker>
- Build artifacts: <rebuilt / not required / deferred>
- Services: <none started — list any the task will require>
- Ready: <yes / partial / no>
- Blockers: <anything preventing work>
```

## Failure Modes to Catch

- `node_modules` exists but was installed against a different Node version — symptom: native module errors. Fix: delete and reinstall.
- `.env.local` exists but is stale (missing keys added in main since the worktree was created). Only detectable by diffing; flag if the task hits env-related errors.
- Python venv activated from the main worktree leaks into the subshell — always check `which python` resolves inside the current worktree.
