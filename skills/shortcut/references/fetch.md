---
tier: Light
---

# Shortcut API Fetch

Use this helper whenever a workflow needs to make Shortcut REST API calls. It wraps the known operational gotchas so callers don't rediscover them each session.

Global rules only route Shortcut work here; this file owns the detailed REST protocol.

## Before Making Calls

1. Confirm `$SHORTCUT_API_TOKEN` is set
2. Source the retry wrapper below — use it for every call in the session

## Retry Wrapper

The Shortcut API returns `organization2_missing` (or similar transient errors) on the first call of a session. This is normal. Always use this wrapper, and always pass `--fail-with-body` (curl 7.76 or newer): plain `curl -s` exits 0 on an HTTP error, so a failed call would never be retried or noticed.

```bash
shortcut_call() {
  local result attempt
  for attempt in 1 2; do
    # --fail-with-body makes curl exit non-zero on HTTP 4xx/5xx and still
    # print the error body; organization2_missing is the transient one.
    if result=$("$@") && [[ $result != *organization2_missing* ]]; then
      printf '%s\n' "$result"
      return 0
    fi
  done
  printf 'Shortcut API failed after retry: %s\n' "$result" >&2
  return 1
}
# Usage: shortcut_call curl -sS --fail-with-body -H "Shortcut-Token: $SHORTCUT_API_TOKEN" ...
```

If the retry also fails, surface the gap to the user — do not silently move on with missing data.

## JSON Parsing

Shortcut responses contain control characters (newlines, tabs) in text fields like `description` and `comments[].text`. Raw `jq` parsing will fail on these.

**Use Python with `strict=False`:**
```bash
python3 -c "
import json, sys
data = json.loads(sys.stdin.read(), strict=False)
# ... process data
" <<< "$result"
```

Do not attempt `jq` on fields that contain user-authored text. Use `jq` only for simple structural queries on well-typed fields (IDs, dates, booleans).

## Known Field Shape Gotchas

| Field | Gotcha |
|-------|--------|
| `labels` | Array of objects: `[{"id": ..., "name": "..."}]` — use `.labels[].name`, but **guard for null**: `(.labels // [])[] .name` |
| `comments` | On the full story from `GET /stories/<id>`. Search results (`StorySlim`) have no comments, and no `description` unless the search asks for `includes_description: true`. |
| `external_links` | Array of strings (GitHub PR URLs). Can be empty `[]`. |
| `owner_ids` | Array of member UUIDs, not names. Cross-reference with `GET /members` to resolve. |
| `group_id` | Single UUID or `null` if unassigned. Not an array. |
| `epic_id` | Integer or `null`. |
| `estimate` | Integer or `null`. Not all story types use estimates. |
| `workflow_state_id` | Integer. Map to name via `GET /workflows`. Cache the mapping per session. |
| `custom_fields` | Array of `{"field_id": ..., "value_id": ..., "value": "..."}`. Shape varies by workspace config. |
| `description` | Markdown string. May contain control chars, emoji, and embedded images. Always parse with `strict=False`. |

## Endpoints

| Endpoint | Method | Use |
|----------|--------|-----|
| `/stories/search` | POST | Find stories by team, state, dates. Returns every match as one `StorySlim[]` array, with no `next`. |
| `/search/stories` | GET | Search-operator query (`?query=...&page_size=25`). Paged with `next`. |
| `/stories/<id>` | GET | Single story details |
| `/epics/<id>` | GET | Epic details — progress, state, stories |
| `/groups` | GET | All teams (groups) — verify UUIDs |
| `/groups/<id>/stories` | GET | Stories assigned to a team |
| `/iterations` | GET | All iterations |
| `/workflows` | GET | Workflow states — map state IDs to names |
| `/members` | GET | All workspace members |

## Common Query Patterns

**Completed stories by team in a date range:**
```bash
shortcut_call curl -sS --fail-with-body -X POST "https://api.app.shortcut.com/api/v3/stories/search" \
  -H "Content-Type: application/json" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
  -d '{"completed_at_start":"2026-03-01T00:00:00Z","completed_at_end":"2026-03-21T23:59:59Z","group_id":"<team-uuid>"}'
```

**WIP stories by team:**
```bash
shortcut_call curl -sS --fail-with-body -X POST "https://api.app.shortcut.com/api/v3/stories/search" \
  -H "Content-Type: application/json" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
  -d '{"workflow_state_types":["started"],"group_id":"<team-uuid>"}'
```

**Blocked stories:** Query WIP, then filter client-side for `.blocked == true` or `.blocker == true`.

## Pagination

Only `GET /search/stories` pages. Its response has `data` and `next`; `next` is a path plus query string (`/api/v3/search/stories?...`), or null on the last page. Request `https://api.app.shortcut.com` + `next` until it is null.

`POST /stories/search` does not page: it returns a plain array of every match. Keep its filters narrow (team, state, date range) rather than looking for a `next` field.

## Workflow States

Fetch from `/workflows` to map `workflow_state_id` to human-readable names. The "Engineering Kanban" workflow is primary. Typical flow: Unstarted -> Ready for Dev -> In Development -> Ready for Review -> In Review -> Ready for Deploy -> Deployed/Done.

## Story ID Formats

Stories can be referenced as:
- `sc-12345` or `SC-12345` — extract the number, query `/stories/12345`
- Shortcut URL — extract the story ID from the path
- Numeric ID — query directly

## MCP Fallback

When REST API is unavailable after retry or for interactive one-off lookups, use the Shortcut MCP tools:

| Tool | Use |
|------|-----|
| `stories-search` | Search with team, date, state filters |
| `stories-get-by-id` | Single story details |
| `epics-get-by-id` | Epic details |
| `epics-search` | Find epics by query |
| `iterations-search` | Find iterations by date range |
| `iterations-get-stories` | Stories in an iteration |

## Minimal Fetch Pattern

```bash
# 1. Set up wrapper
shortcut_call() {
  local result attempt
  for attempt in 1 2; do
    if result=$("$@") && [[ $result != *organization2_missing* ]]; then
      printf '%s\n' "$result"
      return 0
    fi
  done
  printf 'Shortcut API failed after retry: %s\n' "$result" >&2
  return 1
}

# 2. Fetch story
story=$(shortcut_call curl -sS --fail-with-body \
  "https://api.app.shortcut.com/api/v3/stories/12345" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN")

# 3. Parse safely
python3 -c "
import json, sys
s = json.loads(sys.stdin.read(), strict=False)
print(f\"Story: {s['name']}\")
print(f\"Type: {s['story_type']}\")
print(f\"Labels: {', '.join(l['name'] for l in (s.get('labels') or []))}\")
print(f\"Links: {s.get('external_links', [])}\")
" <<< "$story"
```
