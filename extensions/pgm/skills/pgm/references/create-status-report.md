# Live Program Health Report

Before executing, read the [program management context](../../../rules/pgm.md). Use the [Shortcut collection reference](../../../../../skills/shortcut/references/fetch.md) for API retry, pagination, parsing, and field-shape rules.

> **When**: Before meetings, weekly check-ins, or anytime you need a current snapshot of program health.
> **Produces**: Program health report with epic progress, flow health, risks, blockers, and team state.

## Effect Boundary

Effect: `local_mutation`.

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
- Read `$PGM_DIR/config.json` for team UUIDs, members, bots, repositories and
  `thresholds` (defaults in `rules/pgm.md`).
- Parse arguments: team filter, epic filter, or all teams. "Current state" is
  today; "recently shipped" is the last 14 days.

### 2. Collect Data

The parent runs every collection call; independent calls (per team, per
repository, per epic) run concurrently when supported.

- **Shortcut** (follow the Shortcut collection reference): per team,
  `POST /stories/search` with `workflow_state_types: ["started"]` and
  `group_id` (WIP), and with `completed_at_start` 14 days ago and `group_id`
  (recently completed, with `cycle_time`, `story_type`, `epic_id`,
  `estimate`). Then `GET /epics/{id}` for each unique `epic_id`, and
  `GET /workflows` once to name the states.
- **GitHub**, per configured repository:
  `gh pr list -R <repo> --state open --limit 100 --json number,title,author,createdAt,reviewDecision,url,labels`
  and `gh pr list -R <repo> --state merged --limit 200 --json number,title,author,mergedAt,url --search "merged:>YYYY-MM-DD"` (14 days ago).
- **Docs** (optional): any connected docs search for recent meeting notes,
  prior reports or open action items; skip it when none is connected or
  nothing relevant comes back.

Drop bot-owned stories and bot-authored PRs.

<!-- aitk-model-route:pgm.status-collection -->
When the runtime supports independent workers, dispatch the collected payloads to 2-3 read-only summarization workers on `operations` in one scheduling step (Shortcut, GitHub, docs); otherwise summarize them sequentially. Each worker returns structured JSON or markdown for the parent to synthesize, flagging: stories whose `moved_at` is older than `stalled_days`; `blocked` or `blocker` stories; WIP per member from `owner_ids`; PRs open longer than `pr_review_hours` without an approving review; and the review backlog (`reviewDecision` empty or `REVIEW_REQUIRED`).

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
  - [Flag a team whose WIP exceeds team_wip_multiplier × its member count]
- **Cycle Time**: [median] days (last 14 days)
- **Throughput**: [count] stories completed in last 14 days
- **Stalled**: [count] stories with no movement > stalled_days
  - [List each with owner and current state]

## Risks & Blockers
Auto-detected from signals:
- Blocked stories (from Shortcut `blocked`/`blocker` fields)
- Stalled work (no state change > stalled_days)
- Review backlog (PRs pending review > pr_review_hours)
- High WIP (team WIP > team_wip_multiplier × team size)
- Epics at risk (low completion rate vs timeline)

For each risk:
- **[Risk]** — [Impact] — [Owner/Team] — [Suggested action]

## Team State
Per team:
- **[Team name]** — [WIP count] in progress, [completed count] shipped (14d)
  - [Who's working on what — from story owners]
  - [Capacity signals — anyone over member_wip_max WIP items?]

## PR State
- **Open**: [count] across repos ([count] awaiting review > pr_review_hours)
- **Merged (14d)**: [count]
- **Review backlog**: [list PRs needing attention]

## Recently Shipped
- [Story/PR name] — [team] — [completed date]
  (Group by team, most recent first, limit to ~10 most notable)
```

### 4. Report and Follow Up

Present the report. With `--audience <mode>`, format it with
[comms.md](comms.md) for that audience. Otherwise present the detailed report
and offer follow-ups: an audience summary through [comms.md](comms.md), a
deeper look at the biggest risks, or one team or epic expanded.

## Notes

- This is a live snapshot as of query time; for historical metrics and trends,
  use `$pgm create-velocity-report`.
- The report names risks from signals; it does not prescribe solutions.
