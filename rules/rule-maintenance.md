# Rule Maintenance

Rules are living documents driven by evidence, not by intuition mid-task.

## Signal Source

High-signal events go to the observation queue owned by the `reflection` skill
(`.ai-toolkit/observations.jsonl`): a user correction, a skill misroute or
manual override, a reclassification, the same gate failing twice, a specialist
invalidating an RCA or plan assumption, a repeated manual workaround, a
low-yield review lane. Periodic `reflect` review clusters them; a cluster is the
evidence a rule change needs.

## When a rule is violated

Strengthen the language, add the failure as a concrete negative example, and
consider loading it earlier. Add the eval case that would have caught it.

## When a rule is stale

Update it to current behavior, remove dead thresholds, and say so in the summary.

## When a new pattern emerges

Check existing rules for partial coverage first. A rule belongs in `rules/` only
when it applies across skills; workflow sequences and domain methods belong in
skills. Keep one concern per file, 20 to 40 lines, kebab-case names.

## Promotion

Rule and skill changes require human approval and ship with an eval candidate
under `evals/`. Never mutate rules or skills automatically from observations.
Scope is the toolkit's `rules/`; never edit a project's own guidance.
