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

The GitHub API for Preset's repos — `superset-shell`, `superset-private`, `manager` — is reachable **only from the corporate VPN**. Jenkins mirrors build status back onto the PRs as commit statuses, but reading any of it still needs VPN-level API access.

Consequence for automation: **anything cloud-executed cannot read these repos.** A
cloud-backed `recurrence` binding runs off the VPN and cannot authenticate to the
API. Do not recommend it for workflows that must read a Preset repo (PR
watching, CI polling, release audits).

Automation that must read these repos runs **locally** on a host connected to the VPN: an in-session recurrence capability or a local scheduler invoking the provider's headless runner. A local runner only fires while the machine is awake and VPN-connected, so scheduled runs must report missed/offline executions rather than silently implying coverage.

Public repos (e.g. the toolkit's own) are unaffected; cloud scheduling is fine there.

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
