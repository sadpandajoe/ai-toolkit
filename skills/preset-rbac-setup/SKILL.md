---
name: preset-rbac-setup
description: Seeding the canonical RBAC test users (workspace roles + data access roles) on a fresh Preset staging workspace via the Manager API, before RBAC-related QA. Do NOT use for changing roles on real customer workspaces, creating new test accounts (the seven test logins must already exist), or generic team administration.
---

# Preset RBAC Setup

Seeds the canonical seven test users with workspace roles and (where applicable) a default data access role (DAR) on a target Preset workspace. The mapping originated in the cypress RBAC tests of the old e2e repo; it lives here because that repo is going away.

## Use it when

- A fresh staging or dev test workspace needs the canonical RBAC users before RBAC-related QA.
- A rerun should bring an existing test workspace back to the canonical roles.

Not for real customer workspaces, creating test accounts (the seven logins must already be team members), or generic team administration.

## Run it

```bash
node <toolkit-root>/scripts/preset/setup-rbac.mjs --host <workspace-host-or-url> [--apply] [--replace-existing] [--headless]
```

`scripts/preset/setup-rbac.mjs` does the work: login, token discovery, team and workspace lookup, the plan, the writes, the SYNCING to APPLIED polling, and the result table. Do not write a replacement script from this page.

- **Dry-run by default.** Without `--apply` it prints the plan table (user, current role, proposed role, DAR action, permission name, deletion candidates) and changes nothing.
- `--apply` authorizes exactly the role and DAR changes in that plan, after checking discovery has not changed since the plan. `--replace-existing` additionally deletes the stale toolkit-owned DARs listed in the plan; it is refused without `--apply`.
- **Refusals.** The host must be an `app-stg` or `app-dev` workspace (`scripts/preset/hosts.mjs`); the script refuses `app.preset.io`, `manage.app.preset.io` and any other pattern before a browser starts. There is no production override, and no confirmation-based escape hatch.
- **Manager URL** comes from the host: `app-stg` → `https://manage.app-stg.preset.io`, `app-dev` → `https://manage.app-dev.preset.io`.
- **Credentials** (never printed): `QA_LOGIN` / `QA_PASSWORD` when set, otherwise `PRESET_STG_BOT_LOGIN` / `PRESET_STG_BOT_PASSWORD` on staging. The login must be a member of the team that owns the workspace, with privilege to update memberships and create permissions.
- Playwright is imported normally (a `node_modules` above the script), else from `~/.qa-runner/node_modules`. Login state persists at `~/.qa-runner/storage/<manager-host>.json`, so reruns skip the login.
- Result statuses per user: `UNCHANGED`, `UPDATED`, `NOT_A_MEMBER`, `ROLE_FAILED`, `DAR_FAILED`. `NOT_A_MEMBER` means the user must be invited to the team first; this skill does not invite.

Before running, check the workspace is genuinely a test workspace (for example an `app-stg.preset.io` host with a hex-style slug) and whether the user wants all seven canonical users or a subset.

## Canonical user → role mapping

| Email | Workspace role | DAR? |
|-------|----------------|------|
| `test-primary-contributor@preset.zone` | `PresetAlpha` | yes |
| `test-limited-contributor@preset.zone` | `PresetGamma` | yes |
| `test-limited-contributor-no-access@preset.zone` | `PresetGamma` | **no** |
| `test-dashboard-viewer@preset.zone` | `PresetDashboardsOnly` | yes |
| `test-dashboard-viewer-no-access@preset.zone` | `PresetDashboardsOnly` | yes (test name "no access" refers to the dashboards exercised, not the DAR) |
| `test-viewer@preset.zone` | `PresetReportsOnly` | yes |
| `test-no-access@preset.zone` | `PresetNoAccess` | **no** |

Workspace role identifiers are Preset-specific names (not Superset's `Admin`/`Alpha`/`Gamma`). Use exactly these strings.

## DAR grant shapes

A DAR's `acl[dar:<name>].grants` array holds one or more `{resource, action}` objects. The cypress tests use these variants:

**Default per-datasource grants** (the script's default). Four datasources on the `examples` DB:

```json
[
  {"resource": "database:examples:schema:public:datasource:Sample Geodata",                    "action": "datasource_access"},
  {"resource": "database:examples:schema:public:datasource:Flights",                           "action": "datasource_access"},
  {"resource": "database:examples:schema:public:datasource:San Francisco BART Lines",          "action": "datasource_access"},
  {"resource": "database:examples:schema:public:datasource:San Francisco Population Polygons", "action": "datasource_access"}
]
```

**Whole-database grant**, for primary/limited-contributor tests that create their own DB:

```json
[{"resource": "database:<dbName>", "action": "database_access"}]
```

**Resource strings:** database `database:<dbName>`; datasource (table) `database:<dbName>:schema:<schemaName>:datasource:<tableName>`; schema `database:<dbName>:schema:<schemaName>` with `schema_access` (exists in the API, unused by the RBAC tests).

## Manager API contract

All RBAC writes go to **Manager**, not the workspace's Superset API. Paths are relative to the Manager URL.

| Step | Method | Path | Body / query |
|------|--------|------|--------------|
| List teams the login belongs to | GET | `/api/v1/teams/` | — |
| List a team's workspaces | GET | `/api/v1/teams/{teamSlug}/workspaces/` | — |
| List team memberships (email → user_id, username) | GET | `/api/v1/teams/{teamSlug}/memberships/` | — |
| Set workspace role | PUT | `/api/v1/teams/{teamSlug}/workspaces/{workspaceId}/membership` | `{role_identifier, user_id}` |
| List permissions on a workspace | GET | `/api/v1/teams/{teamSlug}/permissions/` | qs: `workspace_name`, `permission_type` (`data_access_role` / `row_level_security`), `grantee_identifier` |
| Get one permission | GET | `/api/v1/teams/{teamSlug}/permissions/{permissionName}` | — |
| Create data access role | POST | `/api/v1/teams/{teamSlug}/permissions/` | DAR body |
| Update data access role | PUT | `/api/v1/teams/{teamSlug}/permissions/{permissionName}` | DAR body |
| Delete data access role | DELETE | `/api/v1/teams/{teamSlug}/permissions/{permissionName}` | — |

DAR body (`type: "data_access_role"`); the `dar:` prefix and the `acl` shape are required:

```json
{
  "workspace_name": "<workspace.name>",
  "type": "data_access_role",
  "grantees": [{"type": "USER", "identifier": "<user.username>"}],
  "acl": {
    "dar:AI Toolkit RBAC <user.username>": { "config": {}, "grants": [ ...GRANTS ] }
  }
}
```

The stable toolkit-owned name `AI Toolkit RBAC <username>` makes a rerun PUT the same permission instead of POSTing a duplicate (POST is not idempotent; the membership PUT is). Permissions without that prefix are unrelated and are never deleted or rewritten. An empty DAR (`grantees: []`, `grants: []`) only pairs with a separately created RLS rule; plain seeding never creates one.

**Permission install is async:** after a POST or PUT the permission goes `SYNCING` → `APPLIED` (or `FAILED` / `TIMEOUT`). The script polls `GET /permissions/{name}` every 5 seconds for up to 12 tries and reports the terminal status; a fire-and-forget write is never reported as seeded.

## Auth model (the gotcha)

Manager auth is session cookies plus one short token used in two headers. The token comes from `localStorage.access_token` (older builds, what the cypress code expects), else the `csrf_access_token` cookie (newer Manager builds; observed 2026-05 on app-stg, re-verify). The same token goes into:

- `Authorization: Bearer <token>`
- `X-CSRF-Token: <token>` (writes only), with `Referer: <workspace URL>` on writes (any workspace URL on the same Manager works).

The login page is two-step: email → "Next" → password → "Log in" (re-verify if the script's login fails).

## Out of scope

- **Row Level Security (RLS) rules** live on the *workspace's Superset API* at `/api/v1/rowlevelsecurity/`, with a separate workspace session that shares no auth with Manager. Manager's `row_level_security` permission type is only a metadata wrapper; the rule itself is POSTed to the workspace. Scope an RLS request separately.
- **Inviting users to a team** and **workspace creation**: both are assumed done.
