# Context Management

At every chain boundary or loop iteration, update durable state before applying
the provider's `context_reset` capability. Chat history is disposable; declared
artifacts are authoritative.

## Proactive Phase Reset Policy

- **TRIVIAL**: stay in one session unless tool or log output becomes unusually large.
- **STANDARD**: reset when logs, diffs, or review rounds become noisy, especially before independent review.
- **COMPLEX / expensive**: reset at every gate transition, after the current
  artifact and machine checkpoint are current.

A gate transition is the natural reset boundary because it's already the point
where durable state must be current: a `PASS` closes a checkpoint and opens
the next phase; a `RETRY`/`ESCALATE` records a repeat-failure count that must
survive the reset or the counting rule breaks. For COMPLEX work, reset after
recording the gate decision (`rules/gates.md`'s block, persisted via
`aitk gate-state`), not mid-attempt. Concretely, that means:

1. Investigation or planning artifact written, gate recorded.
2. Plan/RCA review gate recorded (`PASS`, or `RETRY`/`ESCALATE` with reason
   and count persisted).
3. Implementation slice or wave completed, verification gate recorded.
4. Review gate recorded with findings and fix queue.
5. Review fixes completed, next validation/reporting gate recorded.

Batch work resets between waves. Skip a reset only when the next phase is tiny
and the durable artifact already contains everything needed, including any
in-progress gate's reason/count; record the reason in `PROJECT.md`.

## Reactive Thresholds

- Below roughly 70% context and below $3 estimated session cost: continue.
- At or above roughly 70%, or above $8: finish the in-flight action, checkpoint,
  then apply `context_reset`.
- Between $3 and $8: consider whether a fresh context would be cheaper and clearer.

Never cut off an edit, tool call, or review round mid-action. Do not start the
next phase before the checkpoint is durable.

## Save and Continue Protocol

1. Use the deterministic checkpoint API and the selected workflow contract to
   update the `PROJECT.md` machine block and human continuation record. If a
   gate decision is in flight (a `RETRY`/`ESCALATE` mid-count, or a decision
   not yet acted on), persist it with `aitk gate-state` before resetting —
   the repeat-failure count in `rules/gates.md`'s counting rule depends on it
   surviving the reset.
2. Leave uncommitted work untouched unless the workflow already has commit
   authorization; record dirty state instead.
3. Apply the provider's `context_reset` binding or its declared fresh-session fallback.
4. Resume through the `start` workflow, which reloads the checkpoint, declared
   state artifacts, and next phase.

Do not rely on chat memory after a reset. Provider task lists may mirror the
current phase but never replace `PROJECT.md`, `PLAN.md`, or workflow manifests.
Provider-native recurrence, worktree, or session state is likewise a disposable
binding behind the shared capability contract.

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
