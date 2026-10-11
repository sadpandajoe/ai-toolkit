# Worktree Preflight

Run once when entering a new git worktree, before any build, test, or agent
work. A worktree shares `.git` with the main checkout but not dependency
folders (`node_modules/`, venvs), build outputs (`dist/`, `.next/`,
`__pycache__/`) or `.env` files, so a fresh one looks ready and fails on the
first command. Skip it when the worktree was already prepared this session.

```bash
MAIN_WT=$(git worktree list --porcelain | awk '/^worktree / {print $2; exit}')
CUR_WT=$(git rev-parse --show-toplevel)   # equal to MAIN_WT: main checkout, stop here
```

1. **Dependencies**: install only what is missing, with the lockfile's tool
   (`npm install` / `yarn` / `pnpm install`, `pip install -r requirements.txt`,
   `poetry install` or `uv sync`, `bundle install`, `go mod download`). Ask
   before reinstalling over a version mismatch.
2. **Env files**: copy each `.env`, `.env.local`, `.env.development` present in
   `$MAIN_WT` but missing here (`cp "$MAIN_WT/.env.local" "$CUR_WT/"`). Ask
   before copying a file with `production` in its name.
3. **Build artifacts**: rebuild only when the task needs a working app or
   bundle.
4. **Services**: never start them here; list what the task will need.

Failure modes:
- `node_modules` built for another Node version: native-module errors; delete and reinstall.
- A stale `.env.local` missing keys added on main since the worktree was made.
- A venv from the main worktree leaking into the shell: check `which python`.

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
