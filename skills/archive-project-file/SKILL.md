---
name: archive-project-file
description: Move completed-phase PROJECT.md content to PROJECT_ARCHIVE.md, or remove a stale PLAN.md after a workflow is done. Do NOT use for active work, unresolved blockers, current continuation checkpoints, or summaries that should stay in PROJECT.md.
---

# archive-project-file

> **When**: A project/feature is done and needs to be preserved.
> **Produces**: Archived PROJECT.md content in PROJECT_ARCHIVE.md, stale PLAN.md deleted.

## Contract

Keep PROJECT.md focused on active work: move completed-phase detail into
PROJECT_ARCHIVE.md and delete a stale PLAN.md. This skill is the only deletion
path for either. In scope: completed investigations, implementations,
milestones, resolved blockers, and old log sections no longer needed for
active execution. Never archive active work, Current Status, the current
checkpoint, open blockers, or anything the next immediate phase needs; an
active workflow's PLAN.md stays in place.

## Steps

1. **Pick the candidate** from PROJECT.md: a completed investigation,
   implemented feature, finished refactor, or closed milestone. With one
   clear candidate, archive it without asking; ask only when candidates are
   equally plausible or the boundary is unclear.
2. **Choose the sections.** Archive completed investigation timelines, Failed
   Solutions once a solution works, old Development Log entries, resolved
   blockers, and completed implementation notes. Keep Current Status, active
   work, the last few log entries, open blockers, next steps, and the
   checkpoint.
3. **Append the archive entry** to PROJECT_ARCHIVE.md with
   [templates/archive-entry.md](templates/archive-entry.md); never rewrite
   earlier entries, and copy the archived sections verbatim.
4. **Leave the breadcrumb** in PROJECT.md with
   [templates/project-md-after.md](templates/project-md-after.md): phase name
   and completion date, a 1–3 sentence summary, and the pointer to
   PROJECT_ARCHIVE.md.
5. **Handle a stale PLAN.md.** When `PLAN.md` exists at the repo root and
   `bin/aitk project-state show` reports no snapshot or no unfinished
   workflow, delete it and append `Completed: <date> — <feature>` to
   PROJECT.md if absent. Its record lives in git (commits, PR description),
   so its content is not preserved. When a workflow is still active, leave
   PLAN.md in place and tell the user.
6. **Log the archiving** in the Development Log:

   ```markdown
   ### [YYYY-MM-DDTHH:MM] — Archived: [Phase Name]
   - Moved [X] sections to PROJECT_ARCHIVE.md
   - Reason: [concrete, such as "phase complete and merged in PR #123"]
   - PROJECT.md focus now: [one phrase]
   ```
