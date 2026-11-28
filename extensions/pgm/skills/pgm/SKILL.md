---
name: pgm
description: Program-management reports from configured delivery data (Shortcut and GitHub) — a live program health/status report, a monthly velocity report, or either reformatted for an audience (executive, leadership, delivery team, eng+QA, broad stakeholders, escalation). Use for program status, delivery health, velocity metrics or program comms. Do NOT use for product implementation, code review, or when no PGM config directory exists.
---

# Program Management Reports

| Request | Reference |
|---------|-----------|
| Current health: epics, flow, risks, team state (`[team] [--epic <name>] [--audience <mode>]`) | [references/status-report.md](references/status-report.md) |
| Monthly velocity (`[--month YYYY-MM] [--summary-only] [--audience <mode>]`) | [references/velocity-report.md](references/velocity-report.md) |
| Any of it for one audience | [references/comms.md](references/comms.md) |

## Before collecting anything

Run `python3 <skill-dir>/scripts/preflight.py status|velocity` (add
`--shortcut-connector` or `--github-connector` when this session has that
connector instead of a token or `gh`). Exit 1: stop with the findings it
prints, before any collection and with no report written. Exit 0 prints the
effective thresholds.

## Config and thresholds

`$PGM_DIR/config.json` is the only source for teams, members (handles,
Shortcut IDs, roles such as QA, PM, Designer, EM), repositories, bots, dates
and org notes. Read it every run; never hardcode members, team counts,
repository counts or a sprint model. Default to flow signals: WIP, cycle time,
throughput, stalled work, blockers.

The optional `thresholds` object overrides these defaults (the preflight
rejects an unknown key or a non-positive value):

| Key | Default | Flags |
|---|---|---|
| `stalled_days` | 5 | a started story whose `moved_at` is older |
| `pr_review_hours` | 48 | an open PR without an approving review for longer |
| `team_wip_multiplier` | 2 | team WIP above this times the team's member count |
| `member_wip_max` | 3 | a member with more WIP items |

## Collection rules

- Prefer the Shortcut REST API when its token is available, else a connector;
  report any capability gap. Use the `shortcut` skill's rules for retries,
  pagination and field shapes.
- `POST /stories/search` returns every match in one array with no pages, so
  filter it by team, state and dates; only `GET /search/stories` pages (via
  `next`).
- Exclude the `bots` accounts from every metric.
- "Current state" queries use today's date; historical ones use the config
  dates.
- Shortcut `cycle_time` is in seconds; show days.
