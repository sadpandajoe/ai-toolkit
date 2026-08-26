# Rule Maintenance

Rules are living documents. Update them based on real-world usage:

## Drift-catching mechanism

Two signals catch rule drift without waiting for a human to notice:

- **Gate escalation history.** Every checkpoint that cites `rules/gates.md`
  can emit a `gate` event via `skills/metrics-emit` (`state: ESCALATE`,
  grouped by `gate` name); the `metrics` workflow's Gate Reliability table
  surfaces the escalation rate per gate. A gate that keeps escalating for
  the *same* reason across many runs (not one agent's one-off mistake)
  means the rule backing that checkpoint is too weak or stale — treat a
  persistently high escalation rate the same as a manually observed
  violation under "When a rule is violated" below.
- **Evals.** `evals/` fixtures are model-judgment regression checks for
  goal-skill behavior, complementing the deterministic `pytest` suite for
  the parts of a workflow that can't be checked by exit status alone. A
  fixture that used to pass and now fails is a concrete instance of "a
  rule is stale" — the rule's guidance no longer matches what the
  workflow actually needs to do.

Neither signal replaces the manual review below; they're what makes drift
visible early instead of only after repeated live failures. **Status:** the
`gate` event type and the Gate Reliability aggregation are built
(`skills/metrics-emit`, `skills/workflows/references/metrics.md`), but no
skill emits a `gate` event yet — the six `rules/gates.md` citers translate
into its vocabulary at their checkpoints without instrumenting them, so the
table is empty in practice, same dual-run status as `rules/gates.md` itself.
No `evals/` fixtures or runner exist in this repo yet either — that signal
is aspirational until they're built.

## When a rule is violated
A rule that agents ignore is too weak. After observing a violation:
- Strengthen the language (add NEVER lists, move critical instructions to top)
- Add the failure pattern as a concrete example of what NOT to do
- Consider whether the rule needs to load earlier or more prominently

## When a rule is stale
Rules drift from reality as code, APIs, and processes change. When you notice a mismatch:
- Update the rule to match current behavior
- Remove conditions or thresholds that no longer apply
- Flag the update in your summary so the user knows

## When a new pattern emerges
Recurring workarounds or repeated feedback across conversations signal a missing rule. When you see a pattern:
- Check if an existing rule covers it (update if partially covered)
- Extract a new focused rule file if it's genuinely new
- Keep it small — one concern per file, 20-40 lines

## Scope
Rule updates are limited to the `rules/` directory in this toolkit. Do not modify project-level provider guidance or vendor system behavior. Rule changes should be proposed to the user during the summary phase, not applied silently mid-workflow.
