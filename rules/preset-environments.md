# Preset Environments

Reference for Preset-specific environments and how to reach them during testing.

## Staging Credentials

When testing **Manager** or **Superset-shell** against a staging environment, use these env vars for authentication — never hardcode credentials:

| Env Var | Purpose |
|---------|---------|
| `PRESET_STG_BOT_LOGIN` | Login / username for staging bot account |
| `PRESET_STG_BOT_PASSWORD` | Password for staging bot account |

Verify that both variables are present without displaying their values:

```bash
test -n "${PRESET_STG_BOT_LOGIN:-}" &&
test -n "${PRESET_STG_BOT_PASSWORD:-}"
```

Never print, interpolate into diagnostic output, or otherwise expose credential
values. Commands may pass them directly to the authentication boundary.

If either is unset, stop and tell the user:

> "Staging credentials not found. Set `PRESET_STG_BOT_LOGIN` and `PRESET_STG_BOT_PASSWORD` in your shell environment, then retry."

Do not fall back to guessing common dev passwords for staging — the bot account credentials are required.

## Network Reachability (VPN)

Preset's private repositories are reachable only from the corporate VPN; what
that means for watching and scheduling is in `skills/pr-watch/SKILL.md`
(Recurrence Reachability).

## Environment Detection

Identify which environment is under test by the app URL's host. `*` stands
for one or more host labels (workspace hosts look like
`<ws>.us1a.app-stg.preset.io`). `scripts/preset/hosts.mjs` implements this
table; scripts import it instead of matching hosts themselves.

| Host pattern | Environment | Credentials |
|--------------|-------------|-------------|
| `localhost`, `127.0.0.1`, `0.0.0.0` (any port) | Local dev | Try `admin`/`admin`, `admin`/`general` |
| `*.app-stg.preset.io`, `manage.app-stg.preset.io` | Staging | `PRESET_STG_BOT_LOGIN` / `PRESET_STG_BOT_PASSWORD` |
| `*.app-dev.preset.io`, `manage.app-dev.preset.io` | Dev (not production) | Ask the user; never reuse staging or production credentials |
| `*.app.preset.io`, `manage.app.preset.io`, `app.preset.io` | Production | Do not run automated tests |
| Anything else | Unknown | Treat as production: stop and ask the user |

**Never run automated browser tests against production.**

## Preset Products

| Product | Typical local port | Staging host | Dev host |
|---------|-------------------|--------------|----------|
| Manager | 3000 | `manage.app-stg.preset.io` | `manage.app-dev.preset.io` |
| Superset-shell | 8088 | `*.app-stg.preset.io` (one host per workspace) | `*.app-dev.preset.io` |
