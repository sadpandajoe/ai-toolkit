# Preset Environments

Identify the environment by the app URL's host. `*` stands for one or more
host labels (workspace hosts look like `<ws>.us1a.app-stg.preset.io`).
`scripts/preset/hosts.mjs` implements this table; scripts import it instead of
matching hosts themselves (`node <toolkit-root>/scripts/preset/hosts.mjs <url>`
prints the classification).

| Host pattern | Environment | Credentials |
|--------------|-------------|-------------|
| `localhost`, `127.0.0.1`, `0.0.0.0` (any port) | Local dev | `admin`/`admin`, then `admin`/`general` |
| `*.app-stg.preset.io`, `manage.app-stg.preset.io` | Staging | `PRESET_STG_BOT_LOGIN` / `PRESET_STG_BOT_PASSWORD` |
| `*.app-dev.preset.io`, `manage.app-dev.preset.io` | Dev (not production) | `QA_LOGIN` / `QA_PASSWORD`, or ask the user; never reuse staging or production credentials |
| `*.app.preset.io`, `manage.app.preset.io`, `app.preset.io` | Production | No automated tests, ever |
| Anything else | Unknown | Treat as production: stop and ask the user |

`QA_LOGIN` / `QA_PASSWORD` win on any allowed host; role-specific accounts come
from the team's secrets vault, never hard-coded. Do not guess common dev
passwords on staging.

Check that credentials exist without printing them, and pass them only to the
login itself:

```bash
test -n "${PRESET_STG_BOT_LOGIN:-}" && test -n "${PRESET_STG_BOT_PASSWORD:-}"
```

If they are unset, stop and tell the user to set `PRESET_STG_BOT_LOGIN` and
`PRESET_STG_BOT_PASSWORD` in their shell, then retry.

The Preset login is two-step: email, then *Next*, then password, then *Log in*.

## Products

| Product | Typical local port | Staging host | Dev host |
|---------|-------------------|--------------|----------|
| Manager | 3000 | `manage.app-stg.preset.io` | `manage.app-dev.preset.io` |
| Superset-shell | 8088 (backend; the frontend is the node-light port, see `superset-local`) | `*.app-stg.preset.io`, one per workspace | `*.app-dev.preset.io` |
