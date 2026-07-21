# Program Management Context

## Configuration Preflight (Hard Gate)

Before any data collection or report-artifact effect, run `bin/aitk
pgm-preflight --workflow <name> --pgm-dir "$PGM_DIR"`. Add
`--shortcut-connector` or `--github-connector` only when that capability is
actually available. Missing, malformed, unsafe, or incomplete configuration;
missing collection authorization; or an incomplete velocity pipeline stops the
workflow before collection with zero report effects. Never print credential
values in the diagnostic.

When a Python collector is available, call it only through
`aitk.pgm.run_after_preflight` so the full preflight and config validation run
again at the effect boundary. Provider-driven collection must rerun the CLI
preflight immediately before each collection batch. A failed recheck produces
zero collection or report effects.

## Org Structure

Use flow-based delivery signals by default: WIP, cycle time, throughput, stalled work, and blockers. Read the configured team and repository topology at runtime; do not assume a fixed team count, repository count, or sprint model.

### Member Resolution

**Canonical source**: `$PGM_DIR/config.json`. It owns team identifiers, mention names, repository mappings, members, bot accounts, roles, date ranges, and any organization-specific notes.

Always read `config.json` for the full member list with GitHub handles, Shortcut IDs, team assignments, and notes (QA, PM, Designer, EM roles). Do not hardcode member lists — the config is the source of truth.

Bot accounts to filter from metrics: listed in `config.json` under `bots`.

### Repository Mapping

Read each configured repository's name, local path, team relationship, and collection strategy from the `repos` section. Support `per_member` and `all_prs` strategies without embedding organization or repository names in toolkit instructions.

## API Reference

Data-collection workers read `rules/shortcut-api.md` when making Shortcut API calls. See `skills/shortcut/references/fetch.md` for the retry wrapper, JSON parsing, and field shape gotchas. Prefer the Shortcut REST API when its credentials and authorization are available; otherwise use an available connector and report any capability gap.

## Concurrent Collection Pattern

When the runtime supports independent workers, gather independent sources concurrently. Otherwise preserve the same boundaries and execute them sequentially:

```
Worker 1 (Shortcut REST API):
  - Completed stories per team (POST /stories/search with completed_at filters)
  - WIP stories per team (workflow_state_types: started)
  - Blocked/blocker stories
  - Epic details for referenced epics
  - Calculate: WIP per member, stalled stories (moved_at > 5 days ago), type distribution

Worker 2 (GitHub CLI):
  - Open PRs per repo (flag those > 48h without review)
  - Recently merged PRs
  - Review backlog

Worker 3 (workspace search, optional):
  - Prior reports or meeting notes
  - Open action items
  - Skip gracefully if nothing relevant found
```

Each worker should:
- Read `config.json` for team/member context
- Read `skills/shortcut/references/fetch.md` for Shortcut API operational patterns (Worker 1)
- Filter out bot accounts
- Return structured data for synthesis

## Audience Tiers

Used by the internal PGM formatting skill for audience-specific workflow output.
Referenced here so report workflows know what audience modes are available.

| Audience | Focus | Tone |
|----------|-------|------|
| **Executive** | Impact, decisions needed, timeline | Brief, outcome-oriented |
| **Cross-functional** | Dependencies, risks, team highlights | Collaborative, actionable |
| **Delivery** | Board health, blockers, what shipped/next | Direct, owner-tagged |
| **Eng+QA** | PRs, test signals, build health, tech debt | Technical, specific |
| **Broad stakeholder** | What launched, user impact, milestones | Accessible, celebratory |
| **Escalation** | What's at risk, what's been tried, the ask | Urgent, structured |

## Data Collection Rules

1. **Always paginate** — Shortcut search results may span multiple pages
2. **Filter bots** — exclude accounts listed in `config.json` `bots` array from all metrics
3. **State query date** — use today's date for "current state" queries, config dates for historical
4. **Stale threshold** — stories with `moved_at` > 5 days ago and still in progress are flagged as stalled
5. **PR age threshold** — open PRs without review activity > 48 hours are flagged
6. **Cycle time source** — use `cycle_time` field from Shortcut (seconds), convert to days for display
