# Context Management

Autonomous workflows never depend on the user clearing context, and a workflow
never asks for a clear. The parent session stays thin and long-lived; fresh
workers are the phase boundaries; auto-compaction is a safety net; `PROJECT.md`
is the authoritative resume state.

## What Lives Where

- **Parent context**: user intent, the active skill, the routing snapshot, gate
  results, short handoffs, user decisions. Nothing else.
- **Workers**: large logs, diffs, repository exploration, implementation detail.
  They return handoffs, never transcripts (`rules/specialist-handoff.md`).
- **Files**: `PROJECT.md` (state, snapshot, checkpoint), `PLAN.md` (accepted
  plan), workflow manifests (`CI_FIX.md`, `WATCH.md`, `CHERRY_PICK.md`).

## Phase Boundaries

Before every worker dispatch and after every handoff, update the durable
artifact first, then continue. A fresh worker resuming from those artifacts
alone must be able to do the next phase; if it could not, the artifact is
incomplete, not the context.

Reuse a worker only inside the same bounded phase when re-discovery would cost
more than the resume. Start fresh across phases.

## Resume

`start` reads the routing snapshot and checkpoint, re-runs classification only
when the snapshot predates the workflow's contract, and continues at the
recorded gate. Provider task lists mirror state; they never replace files.
