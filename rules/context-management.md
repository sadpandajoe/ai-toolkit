# Context Management

At every chain boundary or loop iteration, update durable state — chat history
is disposable, declared artifacts are authoritative — regardless of whether
anything actually resets the conversation around that boundary.

## Workers as Phase Isolation

The primary isolation mechanism is dispatch, not a manual reset action. A
heavy or expensive phase (investigation, planning, implementation, review)
runs in its own subagent per `rules/specialist-handoff.md`; the orchestrator
never holds that worker's intermediate reasoning or tool output, only its
returned result. This keeps the orchestrator's own context light by
construction, across every complexity tier — TRIVIAL and STANDARD stay light
because their fast paths run few or no subagent phases at all; COMPLEX stays
light because each phase's reasoning load lives in its own worker, not in the
orchestrating context that chains them together.

## Auto-Compact Safety Net

The provider transparently compresses older turns as the session approaches
its context limit — this is a platform guarantee, not a workflow action to
invoke. Do not track a percentage-used or dollar-cost threshold and decide
when to trigger a reset; there is no reliable `context_reset` capability to
call, and auto-compact already handles the case a manual reset was standing
in for. Treat it as a backstop, not the primary mechanism — the primary
mechanism is worker isolation above; auto-compact covers whatever stays in
the orchestrator's own context regardless.

## No Explicit-Reset Dependency

Because compaction can fire silently, mid-session, with no explicit boundary
to hook a checkpoint to, checkpointing cannot be keyed to "before I reset."
Key it to durable-artifact boundaries instead — the same points that would
have been reset boundaries under a manual scheme, but the trigger is now
"this gate/phase reached a recorded outcome," not "context is getting large":

1. Investigation or planning artifact written, gate recorded.
2. Plan/RCA review gate recorded (`PASS`, or `RETRY`/`ESCALATE` with reason
   and count persisted).
3. Implementation slice or wave completed, verification gate recorded.
4. Review gate recorded with findings and fix queue.
5. Review fixes completed, next validation/reporting gate recorded.

A gate transition is the natural checkpoint boundary because it's already the
point where durable state must be current: a `PASS` closes a checkpoint and
opens the next phase; a `RETRY`/`ESCALATE` records a repeat-failure count
that must survive any compaction the provider performs, or the counting rule
in `rules/gates.md` breaks. Checkpoint after recording the gate decision
(persisted via `aitk gate-state`), not mid-attempt.

Batch work checkpoints between waves. Skip a checkpoint only when the next
phase is tiny and the durable artifact already contains everything needed,
including any in-progress gate's reason/count; record the reason in
`PROJECT.md`. Never cut off an edit, tool call, or review round mid-action to
checkpoint early, and never start the next phase before the checkpoint is
durable.

## Save and Continue Protocol

1. Use the deterministic checkpoint API and the selected workflow contract to
   update the `PROJECT.md` machine block and human continuation record. If a
   gate decision is in flight (a `RETRY`/`ESCALATE` mid-count, or a decision
   not yet acted on), persist it with `aitk gate-state` — the repeat-failure
   count in `rules/gates.md`'s counting rule depends on it surviving any
   compaction, session end, or explicit reset alike.
2. Leave uncommitted work untouched unless the workflow already has commit
   authorization; record dirty state instead.
3. If a fresh session does start — by user action, compaction, or any other
   means — resume through the `start` workflow, which reloads the checkpoint,
   declared state artifacts, and next phase. No workflow step depends on a
   reset having happened; the checkpoint is equally correct whether the next
   turn continues in the same context or a fresh one.

Do not rely on chat memory to carry state across any boundary. Provider task
lists may mirror the current phase but never replace `PROJECT.md`, `PLAN.md`,
or workflow manifests. Provider-native recurrence, worktree, or session state
is likewise disposable — durable artifacts are the only thing a resume can
trust.

## Batch Manifest Checkpoints

For large batches, preserve the manifest pointer and next unit/wave, not raw
per-item history:

- cherry-pick trains: `CHERRY_PICK.md`;
- multi-failure CI fixes: `CI_FIX.md`;
- large feature builds: `PLAN.md`;
- PR watches: `WATCH.md`.

Update the relevant manifest before the checkpoint so resume never depends on
discarded conversation state.

## Reference Loading Policy

Public workflow references should load only the short rules needed at entry.
Resolve detailed domain skills through `interfaces/skills.json` when entering
their phase. Provider adapters are never behavior owners; canonical skills and
references are.
