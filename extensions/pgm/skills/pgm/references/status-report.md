# Live Program Health

A snapshot as of query time. "Current" is today; "recently shipped" is the
last 14 days. It names risks from signals; it doesn't prescribe solutions.

## Collect

Independent calls (per team, repository, epic) can run concurrently.

- **Shortcut**, per team: `POST /stories/search` with
  `workflow_state_types: ["started"]` and `group_id` (WIP), and with
  `completed_at_start` 14 days ago and `group_id` (recently completed, with
  `cycle_time`, `story_type`, `epic_id`, `estimate`). Then `GET /epics/{id}`
  for each unique `epic_id`, and `GET /workflows` once to name the states.
- **GitHub**, per configured repository:
  `gh pr list -R <repo> --state open --limit 100 --json number,title,author,createdAt,reviewDecision,url,labels`
  and `gh pr list -R <repo> --state merged --limit 200 --json number,title,author,mergedAt,url --search "merged:>YYYY-MM-DD"` (14 days ago).
- **Docs** (optional): a connected docs search for recent meeting notes, prior
  reports or open action items.

Drop bot-owned stories and bot-authored PRs. Raw payloads are large: summarize
them in fresh workers (one each for Shortcut, GitHub, docs) when available.

Signals to flag: stories whose `moved_at` is older than `stalled_days`;
`blocked` or `blocker` stories; WIP per member from `owner_ids`; PRs open
longer than `pr_review_hours` without an approving review; the review backlog
(`reviewDecision` empty or `REVIEW_REQUIRED`).

## Report shape

```markdown
# Program Health — [date]
[Team or epic filter, if any]

## Epic Progress
- **[Epic]** — [X/Y stories done] — [on track / at risk / blocked]
  - [Key recent completions] · [Remaining work] · [Risk, if any]

## Flow Health
- **WIP**: [total] across [teams] ([per team]; flag a team above team_wip_multiplier × its member count)
- **Cycle Time**: [median] days (last 14 days)
- **Throughput**: [count] stories completed in the last 14 days
- **Stalled**: [count] with no movement > stalled_days (each with owner and state)

## Risks & Blockers
- **[Risk]** — [Impact] — [Owner/Team] — [Suggested action]
  (blocked stories, stalled work, review backlog, high WIP, epics at risk)

## Team State
- **[Team]** — [WIP] in progress, [count] shipped (14d); who's on what; anyone over member_wip_max

## PR State
- **Open**: [count] ([count] awaiting review > pr_review_hours) · **Merged (14d)**: [count]
- **Review backlog**: [PRs needing attention]

## Recently Shipped
- [Story/PR] — [team] — [date] (by team, most recent first, ~10 most notable)
```

With `--audience`, format it per [comms.md](comms.md). Otherwise offer an
audience summary, a deeper look at the top risks, or one team or epic
expanded. Historical trends belong to the velocity report.
