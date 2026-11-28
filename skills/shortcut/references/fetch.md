# Shortcut API Fetch

`<skill-dir>` is the installed shortcut skill; `sc.sh` exits 2 when
`$SHORTCUT_API_TOKEN` is unset.

```bash
SC=<skill-dir>/scripts/sc.sh
$SC get /stories/12345                                 # GET /api/v3/stories/12345
$SC post /stories/search '{"group_id": "<team-uuid>"}'  # JSON body, or @file.json
$SC search 'owner:me is:started'                       # GET /search/stories, all pages
```

`sc.sh` sends `Shortcut-Token` without printing it; retries once (HTTP 4xx/5xx
count as failures); parses with `json.loads(..., strict=False)`,
since `description` and `comments[].text` carry control characters that break
raw `jq`; and joins every `search` page by following `next`.
`SHORTCUT_API_BASE` overrides the host (tests use it).

## Fields

| Field | Shape |
|-------|-------|
| `labels` | Array of label objects: `(.labels // [])[].name` |
| `comments` | Only on the full story (`GET /stories/<id>`); search results (`StorySlim`) have none |
| `description` | Markdown; absent from `POST /stories/search` results unless the body sets `includes_description: true` |
| `external_links` | Array of URL strings (often GitHub PRs), possibly `[]` |
| `owner_ids` | Array of member UUIDs; resolve names with `GET /members` |
| `group_id` | One team UUID or `null` |
| `epic_id`, `estimate` | Integer or `null` |
| `workflow_state_id` | Integer; map to a name with `GET /workflows` once per session |
| `custom_fields` | Array of `{field_id, value_id, value}`; shape varies by workspace |
| `cycle_time`, `lead_time` | Seconds, once the story is complete |

## Endpoints

| Endpoint | Method | Use |
|----------|--------|-----|
| `/stories/search` | POST | Filter by `group_id`, `workflow_state_types` (`started`, `backlog`, `unstarted`, `done`), `completed_at_start` / `completed_at_end`; returns every match as one array, no paging, so keep filters narrow |
| `/search/stories` | GET | Search-operator query (`?query=...&page_size=25`), paged with `next` |
| `/stories/<id>`, `/epics/<id>` | GET | One story or epic |
| `/groups`, `/groups/<id>/stories` | GET | Teams and their stories |
| `/iterations`, `/workflows`, `/members` | GET | Iterations, workflow states, members |

```bash
$SC post /stories/search '{"completed_at_start":"2026-03-01T00:00:00Z","completed_at_end":"2026-03-21T23:59:59Z","group_id":"<team-uuid>"}'
$SC post /stories/search '{"workflow_state_types":["started"],"group_id":"<team-uuid>"}'   # WIP; filter .blocked / .blocker client-side
```

The primary workflow's name may be set as `shortcut.primary_workflow` in the
target repo's `.ai-toolkit/config.json`; when it is missing, ask once.

When REST still fails after the retry, or for one-off interactive lookups, the
Shortcut MCP tools (`stories-search`, `stories-get-by-id`, `epics-get-by-id`,
`epics-search`, `iterations-search`, `iterations-get-stories`) are the fallback.
