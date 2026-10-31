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

Stop before any collection, with no report written, unless all of these hold,
and say which one failed (never print a credential value):

- `$PGM_DIR` is set, is a real directory (not a symlink), and holds a readable
  JSON `config.json` (not a symlink).
- `config.json` has non-empty `teams` (each with `name` and `id` or `uuid`),
  `members` (each with `name`, a GitHub handle as `github` or
  `github_handle`, a Shortcut ID as `shortcut_id` or `shortcut_uuid`, and a
  team assignment via `team`, `team_id`, `team_uuid` or `teams` that names a
  configured team), `repos` (each with `name`, a `path` that exists, a team
  relationship, and `strategy` `per_member` or `all_prs`), and `bots` as a list
  of account names.
- Shortcut access: `SHORTCUT_API_TOKEN`, or a Shortcut connector in this
  session.
- GitHub access: `gh` installed and authenticated (`GH_TOKEN`,
  `GITHUB_TOKEN`, or `gh auth status`), or a GitHub connector.
- Velocity only: `month` as `YYYY-MM`, `date_range` with exactly `start` and
  `end` as `YYYY-MM-DD` (start not after end), and the pipeline files `run.md`,
  `collect_github.py`, `collect_shortcut.py`, `analyze.py` and `report.py` in
  `$PGM_DIR` (regular files, not symlinks).

## Config and thresholds

`$PGM_DIR/config.json` is the only source for teams, members (handles,
Shortcut IDs, roles such as QA, PM, Designer, EM), repositories, bots, dates
and org notes. Read it every run; never hardcode members, team counts,
repository counts or a sprint model. Default to flow signals: WIP, cycle time,
throughput, stalled work, blockers.

The optional `thresholds` object overrides these defaults; an unknown key or a
non-positive value is a config error:

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
