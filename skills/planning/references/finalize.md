---
name: finalize-plan
description: Fresh-eyes final review of a plan for coherence, contradictions, and implementability. Cold read with no prior review history. Returns Go / No-Go with blocking issues and risks. Internal helper called by `skills/workflows/references/review-plan.md` and similar.
user-invocable: false
disable-model-invocation: true
tier: Heavy
---

# Plan Finalization Review

You are a principal engineer doing a **cold read** of this plan. You have NOT seen any prior reviews or iteration history. Evaluate the plan purely on its own merits.

Read before assessing: `rules/gates.md`, `rules/severity.md`

If PROJECT.md exists, read it first. If it does not exist, use the in-conversation context, plan, or diff as primary source.

## Focus Areas

Analyze with fresh eyes:
- **Internal consistency** — do all sections agree with each other?
- **Contradictions** — does one section promise something another section contradicts?
- **Unstated assumptions** — what does the plan take for granted without saying so?
- **Testing ↔ Implementation alignment** — does the testing strategy actually cover the implementation steps?
- **Implementability** — could a developer pick this up and build it without guessing?
- **Completeness** — are there obvious gaps that would block implementation?
- **Scope clarity** — is it clear what's in scope and what's not?
- **Phase decomposition** — is the work broken into small, independently deployable PRs? Flag if:
  - A single phase is too large to review in one sitting
  - Migrations are in a standalone phase without the code that uses them
  - Phases are horizontal layers (all models → all APIs → all UI) instead of vertical slices
  - Any phase would leave the system in a broken state if deployed alone

## What Makes This Different

This is NOT an iterative review. This is a final gate check:
- No prior context or review history
- No bias from watching the plan evolve
- Fresh perspective catches things iterative reviewers miss
- Focus on "could I build this?" not "is this better than before?"

## Output

```markdown
## Plan Finalization

### Summary
[2-3 sentence assessment of overall plan quality]

### Blocking Issues
Issues that MUST be resolved before implementation:
- [Issue + why it blocks implementation]

### Risks
Non-blocking but important concerns:
- [Risk + suggested mitigation]

### Recommendation
**Go** / **No-Go**

[1-2 sentence justification]
```

No numeric score — `Go`/`No-Go` is this cold read's own domain-specific
verdict. The caller translates it into a `rules/gates.md` gate block: `Go` →
`PASS`; the first `No-Go` on this plan → `RETRY`; a second consecutive
`No-Go` (this is a fresh cold read each time, so "consecutive" means across
calls, not within one) → `ESCALATE`, per that rule's Mapping From the Old
Mechanisms section. This file has no memory of prior calls, so it cannot
compute the repeat count itself — the caller tracks it.
