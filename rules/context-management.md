# Context Management

Autonomous workflows never depend on the user clearing context. The parent
session stays thin and long-lived; fresh workers are the phase boundaries;
auto-compaction is a safety net; `PROJECT.md` is the authoritative resume state.

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

## Compaction and Clearing

- Keep auto-compaction on. Set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` lower (for
  example `80`) when the parent grows faster than expected; compaction of the
  parent does not erase worker history.
- Manual compaction is optional hygiene when the parent gets noisy mid-task.
- Clearing the conversation is optional hygiene between unrelated tasks or
  after heavy manual steering. It is never a workflow step, and a workflow never
  asks for it.
- Bound nesting with `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`: goal skill, one
  worker layer, one exceptional child.
- Codex: the same rules apply with its native custom agents; a fresh session
  resumes from `PROJECT.md` through the `start` workflow when needed.

## Resume

`start` reads the routing snapshot and checkpoint, re-runs classification only
when the snapshot predates the workflow's contract, and continues at the
recorded gate. Provider task lists mirror state; they never replace files.

## Reference Loading

Load short rules at entry and domain skills at phase entry through
`interfaces/skills.json`. Provider adapters translate capabilities and never own
behavior.
