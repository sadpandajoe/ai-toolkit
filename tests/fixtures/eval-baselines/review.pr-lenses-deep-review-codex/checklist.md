# Checklist — review.pr-lenses (shared across all four fixture directories)

Derived directly from `evidence/diff.patch` (a synthetic, deliberately-flawed
diff — fake file, fake bug, no real Preset code), before either the `review`-
or `deep-review`-route trials run. Both required findings are chosen to be
lens-invariant: unambiguous regardless of which review lens (`code-quality.md`
or `adversarial.md`) is applied, per PLAN.md's lens-invariance constraint.
`evidence/diff.patch` and this file must be byte-identical across all four
`review.pr-lenses-*` directories (Validation harness checks 7 and 8).

| finding_id | expected_severity | expected |
|---|---|---|
| `off-by-one-loop` | major | `reconcile_ledger_rows` iterates `range(1, len(rows))`, skipping `rows[0]` — an off-by-one bug that undercounts the ledger total by the first row's amount. Flagged regardless of lens: this is a real functional bug, not a style preference. |
| `hardcoded-secret` | critical | `PARTNER_API_KEY = "sk-live-4f8a9c2e1b7d4f6a9c2e1b7d4f6a9c2e"` is a hardcoded credential committed directly into source. Flagged regardless of lens: this is a real security defect, not a judgment call either lens could reasonably skip.

A trial's `checklist_or_rubric_result` records `match: true` for a required
item only if the corresponding finding (same defect, comparable severity)
appears in that trial's output. Additional findings beyond this list never
count against `match` (recall grading, not exact-match) — see PLAN.md's Judge
bullet.
