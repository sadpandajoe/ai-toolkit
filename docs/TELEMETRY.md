# Telemetry Support

Version 0.1.0 cost reports read Claude Code session JSONL files from
`~/.claude/projects/`. They do not read Codex or other provider telemetry and
must report those sources as unavailable rather than infer usage.

`bin/aitk usage` is the per-session view of that data (tokens, premium
share, estimated cost, with `--period 7d|30d|all`). `bin/aitk usage
--by-workflow` is the per-workflow view the v2 spec's §14 cost hypotheses
need: every priced transcript line is attributed to the skill whose
structured `Skill` `tool_use` block most recently preceded it in the same
session (subagent transcripts follow their parent session), and each
workflow row carries invocation count, total/premium tokens, cost, the peak
prompt size seen (`peak_context_tokens`), and the `workflow-summary` events
joined from each project's `.ai-toolkit/metrics.jsonl` by `command` — run
count, summed retries and reclassifications, mean reviewer yield. Lines
written before a session's first skill invocation are reported under
`(unattributed)`, never guessed. `aitk/workflow_usage.py` documents the
attribution rule.

Costs are API-equivalent estimates, not bills. Known promotional prices are
selected from each record's timezone-aware timestamp. A missing, invalid, or
timezone-free timestamp leaves that promotional record unpriced. Unknown model
families are also unpriced; token and message counts remain visible.

Toolkit workflow metrics are separate provider-neutral events stored in
`.ai-toolkit/metrics.jsonl`, with read-only fallback to legacy
`.claude/metrics.jsonl` during migration. `skills/metrics-emit/SKILL.md` is
the canonical source for every event shape; this section only calls out the
two fields most relevant to cost/observability tooling outside that skill.

Every `model` event, when the provider binding surfaces it, carries
`input_tokens`/`output_tokens`/`cache_tokens` for that one call; every
`workflow-summary` event carries `total_tokens` (the run's full spend across
every route) and `premium_tokens` (the subset spent on an `opus`, `fable`, or Codex
`sol` route — matched by model family, not by exact selector). Both are best-effort — a runtime that doesn't report usage
omits the field rather than guessing, so absence is not zero.

`observation` events record a correction signal — the workflow's own
behavior turned out wrong and got fixed — distinct from a normal gate
failure or classification. Each carries a `kind` (`user-correction`,
`skill-misroute`, `reclassify`, `gate-repeat`, `plan-invalidated`,
`manual-workaround`), the `skill`/`phase` it happened in, one-line
`issue`/`suggested_change` fields, and a `status` (`OPEN`, then `ACTIONED`
or `DECLINED` once `skills/reflection` or a human disposes of it, via a
follow-up event whose `ref` points back to the original). `skills/reflection`
is the only reader that clusters these into proposals; nothing else in the
toolkit consumes them today.
