# Rule Maintenance

Rules are living documents. Update them based on real-world usage:

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
