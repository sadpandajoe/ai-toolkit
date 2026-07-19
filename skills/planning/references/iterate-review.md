---
name: iterate-plan-review
description: Iterate a written plan through parallel reviewer subagents until it meets the quality threshold (default 8/10), then run a cold-read finalization. Internal helper called by create-feature, review-plan, and any workflow that produces a plan and needs structured review before proceeding.
user-invocable: false
disable-model-invocation: true
---

# Iterate Plan Review

Shared procedure for running parallel reviewer subagents against a written plan, iterating until threshold, then finalizing with a cold read.

This skill iterates **reviews of a plan**, not iterations of code review. It is an internal helper — callers reference it explicitly; users do not invoke it.

## Inputs

The caller provides:

- **Plan location**: where the plan lives (usually `PLAN.md`; PROJECT.md should point to it rather than duplicate it)
- **Reviewer set**: which reviewers to run. Always + conditional:
  - Always: whichever reviewers the caller designates as mandatory
  - Conditional: add based on what the plan actually touches
- **Scope**: `trivial` / `moderate` / `standard` — determines reasoning effort
- **Optional PM brief review**: when the plan has a feature brief that needs `pm/references/review-feature-brief.md`
- **Optional action gate**: when the caller wants an action gate block after cold read

## Threshold

Default: **8/10 or better** on every applicable reviewer, plus a **Go** from cold read.

## Procedure

### 1. PM Brief Review (optional)

When the caller provides PM context:

<!-- aitk-model-route:planning.pm-brief-review -->
- Spawn `pm/references/review-feature-brief.md` as a subagent on `review`
- Use `review` by default; use `deep-review` only when the brief covers multi-system rollout or material business risk
- Revise the brief until 8/10
- If the brief reaches 8/10 after the first pass, proceed to technical plan review

### 2. Technical Plan Review

<!-- aitk-model-route:planning.technical-plan-review -->
Launch all applicable technical reviewers **in parallel** as subagents using the routes below. Always-on reviewers:

- `plan-review/references/architecture.md`
- `plan-review/references/implementation.md`
- `testing/references/review-testplan.md`

Add conditional reviewers when the plan touches their area:

- `plan-review/references/frontend.md` — React, CSS, UI components
- `plan-review/references/backend.md` — API, database, migrations

**Model routing** (see `rules/model-assignment.md`):

- PM, implementation, and test-plan lanes use `review`.
- Architecture, security-sensitive, adversarial, and final cold-read lanes use `deep-review`.
- Re-run a shallow lane on `deep-review`; do not invent a different model or effort override.

Each reviewer:
- Reads the plan from the location provided by the caller
- Receives the exact inventoried reviewer contract closure inline from the route runner
- Produces a scored review block (X/10 with strengths, issues, suggestions)

### 3. Iterate Until Threshold

After collecting scores:

- **All reviewers ≥ 8/10** → proceed to cold read
- **Any reviewer below 8/10** → revise the plan based on feedback, then re-run fresh reviewers for material revisions. Reuse the same reviewer only to clarify that reviewer's own finding in the same pass.
- Auto-iterate — do not ask the user whether to continue or which reviewers to re-run
- Only stop for a blocking decision that requires user input, or if stop rules in `rules/stop-rules.md` trigger

**Shallow-analysis escalation**: If a reviewer scored low because their analysis was shallow (not because the plan has real issues), re-run that specific reviewer with heavier reasoning rather than revising a plan that doesn't need revising.

### 4. Cold Read

Spawn sibling [finalize.md](finalize.md) as a fresh-eyes final check using `deep-review`.

- **Go** → proceed to step 5
- **No-Go** with blocking issues → revise and re-run sibling [finalize.md](finalize.md)
- **No-Go** after two revisions → stop and surface the blocking issues to the user

### 5. Write Final Scores

Append the scores to the plan location the caller specified. For standard-path workflows this is typically `PLAN.md`. If a moderate path needs durable plan-review scores, reclassify to STANDARD before using this loop.

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

Do NOT write a per-iteration change log. The caller prints a brief summary in conversation for approval / next step instead — the persistent artifact is the scores, not the diff.

### 6. Action Gate (optional)

When the caller requested an action gate, include `action-gate` context after cold read passes. Auto-proceed conditions are owned by `skills/action-gate/SKILL.md` (Auto-Proceed Rule) — follow that rule rather than a restated threshold here.

## Output

Return to the caller:

- Final scores per reviewer
- Cold read verdict (Go / No-Go)
- Action gate verdict (if run)
- Count of iteration rounds
- Any user-blocking decisions that surfaced

## Notes

- This procedure replaces inline "review iteration" logic previously duplicated in `create-feature` step 4 and `review-plan` body. Both commands call this helper.
- The runner derives and inlines the boundary's exact contract closure; callers
  cannot substitute arbitrary files, and routed workers do not load ambient skills.
