---
name: archive-project-file
description: Move completed-phase PROJECT.md content to PROJECT_ARCHIVE.md, or remove a stale PLAN.md after a workflow is done. Do NOT use for active work, unresolved blockers, current continuation checkpoints, or summaries that should stay in PROJECT.md.
---

# archive-project-file

> **When**: A project/feature is done and needs to be preserved.
> **Produces**: Archived PROJECT.md content in PROJECT_ARCHIVE.md, stale PLAN.md deleted.

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.
Read `PROJECT_TEMPLATE.md` — it defines the YAML frontmatter block's default
(empty) shape, which step 7 below resets PROJECT.md to.

This command should be owned by one main agent. Do not split the write across multiple agents — the archive boundary, breadcrumb, and preserved active context must stay consistent.

PROJECT.md carries v2 machine state beyond its prose sections: the YAML
frontmatter (`workflow`, `complexity`, `size`, `execution_shape`,
`reasoning_attempts`, gate-status enums — see `PROJECT_TEMPLATE.md`), plus
three marker-delimited JSON blocks in the body (`aitk-checkpoint:v1` —
`workflow`, `reclassifications`, accepted artifacts; `aitk-gate:v1` — final
`PASS`/`RETRY`/`ESCALATE`/... state per gate; `aitk-routing:v1` — the
complexity/size snapshot). `aitk project-state --file PROJECT.md` reads all
of these back as one JSON payload — use it rather than re-parsing the
markers by hand.

## Contract

### Goal
Keep PROJECT.md focused on active work by moving completed-phase detail into PROJECT_ARCHIVE.md. When a stale PLAN.md exists with no active workflow, delete it.

### In Scope
- completed investigations, implementations, milestones, and resolved blockers
- older log sections that are no longer needed for active execution
- leaving a short summary and reference behind in PROJECT.md
- deleting a stale PLAN.md (no active workflow uses it)

### Out of Scope
- active work
- current status
- current continuation checkpoint
- anything still needed for the next immediate phase
- the PLAN.md of an active workflow — it stays in place while the workflow runs and persists after completion; this skill is the only deletion path, and it only deletes once the plan is stale (step 7)

## When to Archive

**Good times:**
- After a major phase is complete and no longer active
- After feature implementation is merged and follow-up work is minimal
- After major refactoring finishes
- When PROJECT.md becomes hard to navigate
- Before starting a new major phase

**Don't archive yet if:**
- Work still in progress
- Solution not validated
- Tests still failing
- Under active review
- The archived material is still needed for the next immediate phase

## Steps

### 1. Identify what to archive

Infer the best archive candidate from PROJECT.md first. Common candidates: completed investigation, implemented feature, finished refactoring, closed milestone.

Only ask the user if multiple candidates are equally plausible or the boundary is unclear. If there's one clear completed phase, proceed automatically.

### 2. Read current PROJECT.md

Use the `Read` tool to view PROJECT.md contents. Also run `aitk project-state
--file PROJECT.md` to capture the current `workflow`, per-gate final states,
`reasoning_attempts` counts, and any `reclassifications` — this is the v2
machine-state snapshot step 4 folds into the archive summary and step 7
resets.

### 3. Determine sections to archive

| Archive | Keep |
|---|---|
| Completed investigation timelines | Current Status |
| Failed Solutions (once solution working) | Active / In Progress work |
| Old Development Log entries | Recent Development Log (last few entries) |
| Resolved blockers | Open blockers |
| Completed implementation notes | Next steps |
| | Current continuation checkpoint |
| | Anything needed for the next immediate phase |

### 4. Create archive entry

Use the template at [templates/archive-entry.md](templates/archive-entry.md), including its v2 State fields (`workflow`, final gate states, `reasoning_attempts`, reclassifications) from step 2's snapshot. Append to PROJECT_ARCHIVE.md (don't rewrite prior archive entries).

Do not treat any `OPEN` `observation` event (`skills/metrics-emit/SKILL.md`)
or pending proposal (`skills/reflection/SKILL.md`) as archived phase content
to drop — both live outside PROJECT.md, in `.ai-toolkit/metrics.jsonl` and
`.ai-toolkit/proposals/<date>/` respectively, and archiving PROJECT.md does
not dispose of them; only `skills/reflection` (or a human) does. If the
Development Log or Notes sections being archived reference a specific OPEN
observation or proposal, carry that pointer into the archive entry's "Full
Details" rather than letting the reference disappear with the archived text.

### 5. Update PROJECT.md

Replace archived sections with the breadcrumb template at [templates/project-md-after.md](templates/project-md-after.md). Keep only:
- phase name and completion date
- 1–3 sentence summary
- pointer to PROJECT_ARCHIVE.md

### 6. Log the archiving

Append a Development Log entry using [templates/log-entry.md](templates/log-entry.md).

### 7. Handle stale PLAN.md (if applicable)

If a `PLAN.md` exists at the repo root AND no active workflow references it (no Continuation Checkpoint with `Active plan: PLAN.md`):
- Delete it
- Append a "Completed" entry to PROJECT.md if not already present: `<date> — <feature>`

The audit trail of what was built lives in git (commits, PR description). Don't preserve PLAN.md content — it was a working draft, not a record.

If a Continuation Checkpoint references PLAN.md, leave it in place and surface to the user — they may have an unfinished workflow.

### 8. Reset frontmatter for a fresh file

Only when no workflow continues after this archive — no Continuation
Checkpoint remains, and step 7 found no active `PLAN.md` reference — reset
PROJECT.md's YAML frontmatter block to `PROJECT_TEMPLATE.md`'s empty
defaults (every field blank/null, `modifiers: []`, the nested
`reasoning_attempts:` sub-keys present but empty) so the file is ready for
the next workflow to classify from scratch. Leave the `aitk-checkpoint:v1`,
`aitk-gate:v1`, and `aitk-routing:v1` body blocks alone if the next workflow
run recreates them itself; do not hand-edit those markers.

If a workflow is still in progress (a Continuation Checkpoint or an active
`PLAN.md` reference remains), skip this step entirely — this skill archives
completed content, it does not reset live machine state out from under a
running workflow.

### 9. Verify

- [ ] Archive entry written to PROJECT_ARCHIVE.md, including v2 State fields
- [ ] Critical info preserved
- [ ] Pending observation/proposal pointers preserved, not dropped
- [ ] PROJECT.md more concise
- [ ] References resolve
- [ ] Stale PLAN.md handled (deleted or left for active workflow)
- [ ] Frontmatter reset to defaults only if no workflow continues

For a worked before/after, see [examples/worked-example.md](examples/worked-example.md).

## Notes
- Archive completed phases, don't delete the content
- Keep PROJECT.md focused on current work
- Searchable history lives in PROJECT_ARCHIVE.md
- Use when completed phases are cluttering active work, not as a substitute for checkpointing
- Once invoked, auto-archive the clear candidate rather than pausing for routine confirmation
- Ask only when the archive boundary is genuinely ambiguous
