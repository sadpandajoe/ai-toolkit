# Program Management Context

## Configuration Preflight (Hard Gate)

Before any data collection or report-artifact effect, run `bin/aitk
pgm-preflight --workflow <name> --pgm-dir "$PGM_DIR"`. Add
`--shortcut-connector` or `--github-connector` only when that capability is
actually available. Missing, malformed, unsafe, or incomplete configuration;
missing collection authorization; or an incomplete velocity pipeline stops the
workflow before collection with zero report effects. Never print credential
values in the diagnostic.

## Org Structure

Use flow-based delivery signals by default: WIP, cycle time, throughput, stalled work, and blockers. Read the configured team and repository topology at runtime; do not assume a fixed team count, repository count, or sprint model.

### Member Resolution

**Canonical source**: `$PGM_DIR/config.json` owns team identifiers, mention names, repository mappings, members (GitHub handles, Shortcut IDs, team assignments, roles such as QA, PM, Designer and EM), bot accounts (`bots`), date ranges and organization-specific notes. Read it every run; never hardcode member lists.

### Repository Mapping

Read each configured repository's name, local path, team relationship, and collection strategy from the `repos` section. Support `per_member` and `all_prs` strategies without embedding organization or repository names in toolkit instructions.

## Thresholds

Report flags read the optional `thresholds` object in `config.json`; the
preflight refuses an unknown key or a value that is not a positive number.
Absent keys take these defaults:

| Key | Default | Flags |
|---|---|---|
| `stalled_days` | 5 | a started story whose `moved_at` is older |
| `pr_review_hours` | 48 | an open PR without an approving review for longer |
| `team_wip_multiplier` | 2 | team WIP above this times the team's member count |
| `member_wip_max` | 3 | a member with more WIP items |

## Data Collection Rules

1. **Source** — prefer the Shortcut REST API when its credentials and authorization are available; otherwise use an available connector and report any capability gap.
2. **Narrow searches** — `POST /stories/search` returns every match in one array with no pages, so filter by team, state and dates; only `GET /search/stories` pages with `next`.
3. **Filter bots** — exclude the `bots` accounts from all metrics
4. **State query date** — use today's date for "current state" queries, config dates for historical
5. **Cycle time source** — use `cycle_time` field from Shortcut (seconds), convert to days for display
