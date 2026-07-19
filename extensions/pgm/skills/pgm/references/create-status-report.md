# Live Program Health Report

Before executing, read the [program management context](../../../rules/pgm.md). Use the [Shortcut collection reference](../../../../../skills/shortcut/references/fetch.md) for API retry, pagination, parsing, and field-shape rules.

> **When**: Before meetings, weekly check-ins, or anytime you need a current snapshot of program health.
> **Produces**: Program health report with epic progress, flow health, risks, blockers, and team state.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../../../rules/durable-workflows.md).
The phase graph, authorization gates, and effect keys are the
`create-status-report` entry in `interfaces/contracts.json`; use `bin/aitk
checkpoint --with-pgm` for every durable transition and effect record.

## Usage

```
$pgm create-status-report                         # All teams
$pgm create-status-report "Team Name"             # One configured team
$pgm create-status-report --epic "auth migration" # One epic across teams
$pgm create-status-report --audience executive    # Format for a specific audience
```

## Steps

### 1. Prepare and Preflight

- Run `bin/aitk pgm-preflight --workflow create-status-report --pgm-dir
  "$PGM_DIR"`, adding connector flags only for capabilities that are actually
  available. On any nonzero result, stop before collection with zero report
  effects.
- Read `$PGM_DIR/config.json` for team UUIDs, member list, bot accounts, repo mapping
- Parse arguments: team filter, epic filter, or all teams
- Set date context: today's date for "current state", last 14 days for "recently shipped"

### 2. Collect Data (Concurrent Workers When Available)

<!-- aitk-model-route:pgm.status-collection -->
When the runtime supports independent workers, collect source data in the parent/tool layer, then dispatch the 2-3 read-only summarization slices on `operations` in one scheduling step. Otherwise, summarize the same slices sequentially. Each worker brief must include instructions to:
- Read the program management context for API patterns
- Read `$PGM_DIR/config.json` for team UUIDs, members, bots
- Return structured JSON or markdown that the main context can synthesize

**Worker 1 — Shortcut REST API** (via `curl` with `$SHORTCUT_API_TOKEN`):
Follow the Shortcut collection reference for the retry wrapper, JSON parsing, and field shape gotchas.

Run all team queries in **parallel bash calls** (each team's queries are independent):
- **WIP stories** per team: `POST /stories/search` with `workflow_state_types: ["started"]` and `group_id`
  - Flag stories where `moved_at` > 5 days ago as stalled
  - Flag stories where `blocked == true` or `blocker == true`
  - Calculate WIP count per team member (from `owner_ids`)
- **Recently completed** per team: `POST /stories/search` with `completed_at_start` (14 days ago) and `group_id`
  - Include `cycle_time`, `story_type`, `epic_id`, `estimate`

That's two independent search calls per configured team; schedule all independent calls concurrently when supported.

Then, from the results:
- **Epic details**: Collect unique `epic_id` values, then fetch `GET /epics/{id}` for each — these are also independent, run in parallel
  - Track completion percentage, state, remaining story count
- **Workflow states**: `GET /workflows` once to map state IDs → readable names

Handle pagination on all search calls. Filter out bot-owned stories.

**Worker 2 — GitHub CLI** (via `gh`):

Run all repository queries concurrently when supported (each configured repository is independent):
- For each repository from `config.json`:
  - **Open PRs**: `gh pr list -R <repo> --state open --limit 100 --json number,title,author,createdAt,reviewDecision,url,labels`
  - **Recently merged**: `gh pr list -R <repo> --state merged --limit 200 --json number,title,author,mergedAt,url --search "merged:>YYYY-MM-DD"` (14 days ago)

That's two independent `gh` calls per configured repository.

Then aggregate:
- Flag PRs open > 48 hours without approved review
- Filter out bot authors from `config.json` bots list
- Count review backlog: PRs where `reviewDecision` is empty or "REVIEW_REQUIRED"

**Worker 3 — Workspace search** (optional, skip gracefully if nothing found):
- `notion-search` for recent meeting notes, prior program reports, or open action items
- Only include if results are directly relevant
- If no Notion results, return empty — don't block on this

### 3. Analyze and Synthesize Report

Combine worker results into a structured report:

```markdown
# Program Health — [date]
[Team filter if applicable]

## Epic Progress
For each active epic:
- **[Epic name]** — [X/Y stories done] — [status: on track / at risk / blocked]
  - [Key recent completions]
  - [Remaining work summary]
  - [Risk if any]

## Flow Health
- **WIP**: [total] across [teams] ([per-team breakdown])
  - [Flag if any team > 2× member count]
- **Cycle Time**: [median] days (last 14 days)
- **Throughput**: [count] stories completed in last 14 days
- **Stalled**: [count] stories with no movement > 5 days
  - [List each with owner and current state]

## Risks & Blockers
Auto-detected from signals:
- Blocked stories (from Shortcut `blocked`/`blocker` fields)
- Stalled work (no state change > 5 days)
- Review backlog (PRs pending review > 48h)
- High WIP (team WIP > 2× team size)
- Epics at risk (low completion rate vs timeline)

For each risk:
- **[Risk]** — [Impact] — [Owner/Team] — [Suggested action]

## Team State
Per team:
- **[Team name]** — [WIP count] in progress, [completed count] shipped (14d)
  - [Who's working on what — from story owners]
  - [Capacity signals — anyone overloaded (>3 WIP items)?]

## PR State
- **Open**: [count] across repos ([count] awaiting review > 48h)
- **Merged (14d)**: [count]
- **Review backlog**: [list PRs needing attention]

## Recently Shipped
- [Story/PR name] — [team] — [completed date]
  (Group by team, most recent first, limit to ~10 most notable)
```

### 4. Report and Follow Up

Present the report.

If `--audience <mode>` is provided, format the final output using the [communication reference](comms.md).

Otherwise, present the default detailed report and suggest follow-up actions:

- "Summarize this for execs" → use the internal PGM formatting skill with `executive` audience
- "What are the biggest risks?" → deeper analysis from report data
- "Write a status update" → use the internal PGM formatting skill with the requested audience
- "Focus on [team/epic]" → filter and expand that section

## Notes

- This is a **live snapshot** — data is current as of query time, not historical
- For historical metrics and trends, use `$pgm create-velocity-report` instead
- The report identifies risks from signals but doesn't prescribe solutions — that's a conversation
- If Shortcut API is unavailable, fall back to Shortcut MCP tools (slower, permission prompts)
