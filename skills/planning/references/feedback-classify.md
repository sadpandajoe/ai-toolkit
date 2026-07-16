---
name: feedback-classify
description: Classify review findings as code-level (fix in review loop) or plan-level (route back to planning).
tier: Standard
---

# Feedback Classify

Classify each review finding to determine whether it should be fixed in the current review loop or routed back to the planning phase. This routing decision prevents the review loop from trying to fix problems that require re-planning.

## Required Context

The caller provides:
- The list of review findings with severity (`[major]`, `[minor]`, `[nitpick]`)
- The planning artifacts (acceptance criteria, slice definitions, RCA) for reference

## Steps

1. **For each finding**, assess whether it is a code-level issue or a plan-level issue:

   **Code-level signals** — fix in the review loop:
   - Naming, style, or formatting issues
   - Logic bugs within a single function or module
   - Missing edge case handling
   - Test gaps for existing behavior
   - Performance issues in a localized scope
   - Missing error handling or validation

   **Plan-level signals** — route back to planning:
   - Slice boundary is wrong (work in slice A belongs in slice B, or spans both)
   - Acceptance criterion is ambiguous or contradictory
   - Architecture issue (wrong abstraction, wrong layer, wrong pattern)
   - RCA was incomplete (fix addresses a symptom, not the root cause)
   - Fix scope is too narrow (doesn't cover all affected code paths)
   - Fix scope is too wide (changes unrelated behavior)
   - Missing slice (the plan didn't account for a required change area)

2. **Determine the routing recommendation**:
   - If **all findings are code-level**: `continue-review` — fix them in the current loop
   - If **any finding is plan-level**: `rewind-to-planning` — the plan needs revision before more code-level fixes make sense

   A single plan-level finding is sufficient to recommend rewinding. Continuing to fix code-level issues while a plan-level problem exists wastes effort — the re-plan may invalidate the code changes.

## Output

```markdown
## Feedback Classification

| # | Finding | Severity | Classification | Reason |
|---|---------|----------|----------------|--------|
| 1 | [finding summary] | [major/minor/nitpick] | code-level / plan-level | [one-line reason] |

### Summary
- Code-level findings: [N]
- Plan-level findings: [N]
- Recommendation: continue-review / rewind-to-planning

### Plan-Level Details
[For each plan-level finding, explain which planning artifact needs revision and what the revision should address. Omit this section if no plan-level findings.]
```

## Notes
- Severity and classification are independent axes. A `[minor]` finding can be plan-level (e.g., a minor scope creep that indicates a slice boundary issue), and a `[major]` finding can be code-level (e.g., a critical logic bug in one function).
- When in doubt, classify as code-level. Plan-level classification triggers a rewind, which is expensive. Only classify as plan-level when the evidence is clear.
- This skill is consumed by `create-feature` step 6 and `fix-bug` step 15, replacing inline classification prose.
