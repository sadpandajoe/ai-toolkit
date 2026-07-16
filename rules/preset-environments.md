# Preset Environments

Reference for Preset-specific environments and how to reach them during testing.

## Staging Credentials

When testing **Manager** or **Superset-shell** against a staging environment, use these env vars for authentication — never hardcode credentials:

| Env Var | Purpose |
|---------|---------|
| `PRESET_STG_BOT_LOGIN` | Login / username for staging bot account |
| `PRESET_STG_BOT_PASSWORD` | Password for staging bot account |

Read them at test time:

```bash
echo $PRESET_STG_BOT_LOGIN       # verify the var is set
echo $PRESET_STG_BOT_PASSWORD     # verify the var is set
```

If either is unset, stop and tell the user:

> "Staging credentials not found. Set `PRESET_STG_BOT_LOGIN` and `PRESET_STG_BOT_PASSWORD` in your shell environment, then retry."

Do not fall back to guessing common dev passwords for staging — the bot account credentials are required.

## Network Reachability (VPN)

The GitHub API for Preset's repos — `superset-shell`, `superset-private`, `manager` — is reachable **only from the corporate VPN**. Jenkins mirrors build status back onto the PRs as commit statuses, but reading any of it still needs VPN-level API access.

Consequence for automation: **anything cloud-executed cannot read these repos.** A `/schedule` routine runs as a cloud agent off the VPN, so it cannot authenticate against the API — it does not degrade gracefully, it simply never sees the PR. Do not recommend cloud scheduling for any workflow that must read a Preset repo (PR watching, CI polling, release audits).

Automation that must read these repos runs **locally**, on a host that is on the VPN: an in-session loop (`/loop /watch-pr <pr>`), or a `launchd` cron invoking headless Claude. Inherent limit: a local runner only fires while the machine is awake and VPN-connected — scheduled runs fail silently while it is asleep or off-VPN.

Public repos (e.g. the toolkit's own) are unaffected; cloud scheduling is fine there.

## Environment Detection

Identify which environment is under test by the app URL:

| URL Pattern | Environment | Credentials |
|-------------|-------------|-------------|
| `localhost:*` | Local dev | Try `admin`/`admin`, `admin`/`general` |
| `*.stg.preset.io` or `stg.` in hostname | Staging | `PRESET_STG_BOT_LOGIN` / `PRESET_STG_BOT_PASSWORD` |
| `*.preset.io` (no `stg`) | Production | Do not run automated tests |

**Never run automated browser tests against production.**

## Preset Products

| Product | Typical local port | Staging URL pattern |
|---------|-------------------|---------------------|
| Manager | 3000 | `manager.stg.preset.io` |
| Superset-shell | 8088 | `*.stg.preset.io` |
