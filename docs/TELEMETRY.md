# Telemetry Support

Version 0.1.0 cost reports read Claude Code session JSONL files from
`~/.claude/projects/`. They do not read Codex or other provider telemetry and
must report those sources as unavailable rather than infer usage.

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
every route) and `premium_tokens` (the subset spent on an `opus` or Codex
`sol` route). Both are best-effort — a runtime that doesn't report usage
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
