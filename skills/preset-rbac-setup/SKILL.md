---
name: preset-rbac-setup
description: Seed the canonical seven RBAC test users (workspace roles plus data access roles) on a Preset staging or dev test workspace through the Manager API, before RBAC-related QA. Use when a fresh test workspace needs the canonical users, or an existing one should return to the canonical roles. Do NOT use for real customer workspaces, creating or inviting test accounts, RLS rules, or generic team administration.
---

# Preset RBAC Setup

```bash
node <toolkit-root>/scripts/preset/setup-rbac.mjs --host <workspace-host-or-url> [--apply] [--replace-existing] [--headless]
```

The script does the work: login, token discovery, team and workspace lookup,
the plan, the writes, the `SYNCING` → `APPLIED` polling and the result table.
Do not write a replacement script.

- **Dry-run by default.** Without `--apply` it prints the plan (user, current
  role, proposed role, DAR action, permission name, deletion candidates) and
  changes nothing. `--apply` authorizes exactly that plan, after checking
  discovery has not changed since. `--replace-existing` also deletes the stale
  toolkit-owned DARs in the plan; it is refused without `--apply`.
- **Refusals.** The host must be an `app-stg` or `app-dev` workspace
  (`scripts/preset/hosts.mjs`); the script refuses `app.preset.io`,
  `manage.app.preset.io` and anything else before a browser starts. There is
  no production override.
- Before running, check the workspace is genuinely a test workspace (for
  example an `app-stg.preset.io` host with a hex-style slug) and whether the
  user wants all seven users or a subset.
- **Manager URL** follows the host: `app-stg` → `https://manage.app-stg.preset.io`,
  `app-dev` → `https://manage.app-dev.preset.io`.
- **Credentials**, never printed: `QA_LOGIN` / `QA_PASSWORD` when set,
  otherwise `PRESET_STG_BOT_LOGIN` / `PRESET_STG_BOT_PASSWORD` on staging. The
  login must belong to the team that owns the workspace, with privilege to
  update memberships and create permissions.
- Playwright comes from a `node_modules` above the script, else
  `~/.qa-runner/node_modules`. Login state persists at
  `~/.qa-runner/storage/<manager-host>.json`.
- Result per user: `UNCHANGED`, `UPDATED`, `NOT_A_MEMBER` (invite them to the
  team first; this skill does not invite), `ROLE_FAILED`, `DAR_FAILED`.

## Canonical users

The mapping comes from the old e2e repo's cypress RBAC tests. Role identifiers
are Preset names, not Superset's `Admin`/`Alpha`/`Gamma`; use them exactly.

| Email | Workspace role | DAR? |
|-------|----------------|------|
| `test-primary-contributor@preset.zone` | `PresetAlpha` | yes |
| `test-limited-contributor@preset.zone` | `PresetGamma` | yes |
| `test-limited-contributor-no-access@preset.zone` | `PresetGamma` | **no** |
| `test-dashboard-viewer@preset.zone` | `PresetDashboardsOnly` | yes |
| `test-dashboard-viewer-no-access@preset.zone` | `PresetDashboardsOnly` | yes ("no access" names the dashboards exercised, not the DAR) |
| `test-viewer@preset.zone` | `PresetReportsOnly` | yes |
| `test-no-access@preset.zone` | `PresetNoAccess` | **no** |

## DAR grants

A DAR's `acl["dar:<name>"].grants` holds `{resource, action}` objects. The
script's default grants `datasource_access` on four `examples` datasources in
schema `public`: Sample Geodata, Flights, San Francisco BART Lines, San
Francisco Population Polygons. Contributor tests that create their own
database use `[{"resource": "database:<dbName>", "action": "database_access"}]`.

Resource strings: `database:<db>`;
`database:<db>:schema:<schema>:datasource:<table>`;
`database:<db>:schema:<schema>` with `schema_access` (exists in the API,
unused by the tests).

The toolkit-owned name `AI Toolkit RBAC <username>` makes a rerun PUT the same
permission instead of POSTing a duplicate (POST is not idempotent; the
membership PUT is). Permissions without that prefix are never rewritten or
deleted.

## Manager API

All RBAC writes go to Manager, not the workspace's Superset API.

| Step | Method | Path |
|------|--------|------|
| Teams of the login | GET | `/api/v1/teams/` |
| A team's workspaces | GET | `/api/v1/teams/{teamSlug}/workspaces/` |
| Memberships (email → user_id, username) | GET | `/api/v1/teams/{teamSlug}/memberships/` |
| Set workspace role (`{role_identifier, user_id}`) | PUT | `/api/v1/teams/{teamSlug}/workspaces/{workspaceId}/membership` |
| List permissions (`workspace_name`, `permission_type`, `grantee_identifier`) | GET | `/api/v1/teams/{teamSlug}/permissions/` |
| Get, update, delete one | GET / PUT / DELETE | `/api/v1/teams/{teamSlug}/permissions/{permissionName}` |
| Create a DAR | POST | `/api/v1/teams/{teamSlug}/permissions/` |

A DAR body has `type: "data_access_role"`, `workspace_name`, `grantees: [{type:
"USER", identifier: <username>}]` and the `acl` above. Installation is async:
`SYNCING` → `APPLIED` (or `FAILED` / `TIMEOUT`); the script polls every 5 s,
up to 12 tries, and never reports a fire-and-forget write as seeded.

**Auth gotcha.** Manager uses session cookies plus one short token in two
headers. The token is `localStorage.access_token` on older builds, else the
`csrf_access_token` cookie (newer builds; seen 2026-05 on app-stg, re-verify).
It goes in `Authorization: Bearer <token>` and, on writes, `X-CSRF-Token:
<token>` with `Referer: <any workspace URL on that Manager>`. The login page
is two-step: email → *Next* → password → *Log in*.

## Out of scope

Row Level Security rules live on the workspace's Superset API
(`/api/v1/rowlevelsecurity/`) with a separate session that shares no auth with
Manager; Manager's `row_level_security` type is only a metadata wrapper, and an
empty DAR pairs with such a rule. Inviting users and creating workspaces are
assumed done.
