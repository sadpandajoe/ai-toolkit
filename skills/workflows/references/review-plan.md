# One-Off Plan Review


> **When**: You have a `PLAN.md` or PROJECT.md-referenced plan and want a quality review without the full `create-feature` workflow.
> **Produces**: Reviewed `PLAN.md`, all applicable reviewers at 8/10, cold read passed, and final scores in PROJECT.md.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `review-plan` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
review-plan
review-plan --pm
```

`--pm`: Include PM brief review (`pm/references/review-feature-brief.md`) in addition to technical reviewers.

## Required Context

The reviewer lanes launched by this workflow run these lenses, selected per the
scope table below:

- `plan-review/references/architecture.md`
- `plan-review/references/implementation.md`
- `plan-review/references/frontend.md`
- `plan-review/references/backend.md`
- `testing/references/review-testplan.md`
- `pm/references/review-feature-brief.md` — `--pm` only
- `planning/references/finalize.md` — cold-read gate

Scores use `rules/scoring.md`.

## Command Contract

This workflow owns one-off plan review only. It does not create the plan,
implement it, or turn review comments into code changes.

- Read PROJECT.md to find the active plan pointer, then review `PLAN.md` as the formal plan body; do not preload unrelated workflow references.
<!-- aitk-model-route:workflows.review-plan-fresh -->
- Use fresh reviewer subagents for each review pass after material plan revisions.
- Reuse a reviewer only to clarify that reviewer's own finding in the same pass.
- The main thread revises `PLAN.md`; PROJECT.md stores state/pointers and final scores. Subagents return scored findings only.
- Continue after material findings are resolved and the cold read says Go; otherwise stop on blocker, stop rule, or user decision.
- For STANDARD plans or runs that hit 3+ review iterations, follow `rules/context-management.md`: after each review round, persist scores to PROJECT.md (`## Plan Review Round N`), then checkpoint + context_reset before the next revision-plus-rereview cycle. After a cold-read No-Go, checkpoint + context_reset before launching the revision. This is a hard gate — the score history is needed for resume and pattern detection across rounds.

## Steps

### 1. Read the Plan

Read PROJECT.md to find the active plan pointer, then read `PLAN.md` when present. If no `PLAN.md` exists, fall back to plan content embedded in PROJECT.md. Verify the plan contains at least one of:
- `Implementation Plan` or `Accepted Solution` section
- `Test Strategy` section
- `Feature Brief` section

If no plan content found, stop: `"No plan found in PROJECT.md. Write a plan first, then run review-plan."`

### 2. Assess Plan Scope and Select Reviewers

Assess the plan's complexity to determine reviewer depth. Use the substance of the plan, not role labels, to choose reasoning effort per `rules/orchestration.md`.

| Plan scope | Reviewers | Cold read |
|------------|-----------|-----------|
| **Moderate** — single subsystem, well-understood pattern, no architectural decisions | 1 reviewer: [`plan-review/references/implementation.md`](../../plan-review/references/implementation.md) | [`planning/references/finalize.md`](../../planning/references/finalize.md) |
| **Standard** — multi-system, real trade-offs, novel design, or ambiguous constraints | 3+ reviewers: `plan-review/references/architecture.md` + `plan-review/references/implementation.md` + [`testing/references/review-testplan.md`](../../testing/references/review-testplan.md) | `planning/references/finalize.md` |

**Conditional reviewers** (add to Standard plans when applicable):
- `plan-review/references/frontend.md` — if plan touches frontend (React, CSS, UI components)
- `plan-review/references/backend.md` — if plan touches backend (API, database, migrations)
- [`pm/references/review-feature-brief.md`](../../pm/references/review-feature-brief.md) — if `--pm` flag or plan has a `Feature Brief` section with scope/milestones

State the scope assessment, which reviewers are selected, and why before launching.

### 3. Review Iterations

<!-- aitk-model-route:workflows.review-plan-selected -->
Launch selected fresh reviewer subagents in parallel. Use `review` for bounded implementation/test/PM lanes and `deep-review` for architecture, security-sensitive, and final cold-read lanes. Each reviewer:
- Reads only PROJECT.md plus the active plan content needed for its lens
- Receives the exact inventoried reviewer contract closure inline from the route runner
- Produces a scored review block (X/10 with strengths, issues, suggestions)

After collecting scores:
- If all reviewers are at 8/10 or better → proceed to step 4
- If any reviewer is below 8/10 → revise `PLAN.md` based on their feedback, or PROJECT.md only when the plan is embedded there, then re-run fresh reviewers for material revisions. Reuse the same reviewer only to clarify their own finding in the same pass.
- Auto-iterate — do not ask the user whether to continue or which reviewers to re-run
- Only stop for a blocking decision that requires user input, or if stop rules trigger

### 4. Cold Read

Run `planning/references/finalize.md` on `deep-review` as a fresh-eyes final check:
- If **Go** → proceed to step 5
- If **No-Go** with blocking issues → revise the plan and re-run finalize-plan
- If **No-Go** after two revisions → stop and surface the blocking issues to the user

### 5. Update PROJECT.md

Write final review scores to PROJECT.md:

```markdown
## Plan Review Scores
| Reviewer | Score |
|----------|-------|
| Architecture | X/10 |
| Implementation | X/10 |
| Test Plan | X/10 |
| [conditional reviewers] | X/10 |
| Cold Read | Go / No-Go |
```

### 6. Summary

```markdown
## Review-Plan Complete
[1-2 lines: plan quality assessment and whether it's ready for implementation]

### Review Scores
| Reviewer | Score |
|----------|-------|
| [reviewer] | [score] |

### Key Revisions
- [What changed based on review feedback — omit if no revisions needed]

### What to do next
- [Implement via create-feature or start implementation directly]
```

## Non-Negotiable Gates

- [ ] All applicable reviewers at 8/10
- [ ] Cold read passed (Go)
- [ ] PROJECT.md updated with final scores
- [ ] Summary emitted

## PROJECT.md Update Discipline

- After each review round: append a `## Plan Review Round N` block with reviewer scores, key findings, and cold-read result (when run).
- After review iterations complete: write final scores under `## Plan Review Scores`.
- If revisions were made: update `PLAN.md`, or PROJECT.md only when the plan is embedded there.
- Per-round writes are hard gates before checkpoint + context_reset on STANDARD or 3+ round runs.

## Notes
- Standalone command — `create-feature` step 4 does the same work inline, but this is for one-off use
- Does not create or implement the plan — only reviews an existing one
- The runner derives and inlines the boundary's exact contract closure; callers
  cannot substitute arbitrary files, and routed workers do not load ambient skills.
