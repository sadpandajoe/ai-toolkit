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
`.claude/metrics.jsonl` during migration.
