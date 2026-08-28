# Durable Workflow Runtime

For every workflow whose manifest `execution_class` is `durable`, treat its
entry in `interfaces/contracts.json` as the machine-readable phase,
authorization, effect, verification, and reporting contract.

PROJECT.md's frontmatter (`current_phase`, `current_gate`, `attempt`) is the
human-readable mirror of two separate machine blocks: the `aitk-checkpoint:v1`
block this file governs (phase edges and effect reservations, below), and the
`aitk-gate:v1` block `aitk gate-state` maintains (each gate's last decided
state, reason, and repeat count, per `rules/gates.md`'s six-state contract).
Keep the frontmatter's `current_gate`/`attempt` in sync with whatever
`aitk gate-state` last persisted for the active gate — do not hand-edit either
block, and do not let the frontmatter drift from the machine state it mirrors.

- Initialize the live artifact with `bin/aitk checkpoint init --workflow
  <name>` and validate it before resuming. Re-running init for the same valid
  workflow is a no-op so it cannot erase progress. Starting a different run
  requires `--replace`; replacement refuses while any effect is pending. Never
  hand-edit the delimited machine block or use the repository template as live
  state.
- Advance only through declared phase edges with `bin/aitk checkpoint advance`.
  Persist the human-readable state required by the workflow before advancing.
- Complete the contract's authorization and preflight gates before any effect.
  A gate that isn't `PASS` (per `rules/gates.md`) stops the workflow with no
  reservation or effect: `RETRY`/`ESCALATE` return to the gated step,
  `BLOCKED`/`USER_DECISION` stop for the user, `RECLASSIFY` returns to the
  Complexity Gate.
- Before an idempotent effect, durably call `bin/aitk checkpoint reserve` with
  the declared key and a stable operation ID. After execution or reconciliation,
  call `bin/aitk checkpoint apply` with the same key/ID and a digest of the
  confirmed result. A key declares an effect category and may have multiple
  instance-scoped records; use a distinct stable operation ID for every real
  push, post, resolution, retry, or other repeatable effect.
- On resume, reconcile a pending `artifact_lookup` against the named local
  artifact. Reconcile `provider_idempotency` with the provider using the same
  operation ID. For `manual_stop`, or when the provider cannot query or honor
  that ID, stop for explicit user reconciliation and never retry blindly.
- Treat an applied record as final. An identical apply is a no-op; a changed
  operation ID or result is a conflict. Finish the contract's verification and
  reporting gates before declaring the workflow complete.
- When a Planning phase's RCA, decomposition, or phase plan is accepted, call
  `bin/aitk checkpoint accept-rca` / `accept-decomposition` / `accept-phase-plan`
  with a pointer to the artifact. Each is final once set — a revised plan is a
  new checkpoint phase or a `record-reclassification`, not an overwrite of the
  same field. Record every verification-loop gate outcome's evidence pointer
  with `bin/aitk checkpoint record-evidence`, and every
  `rules/complexity-gate.md` reclassification (reason + from→to) with
  `bin/aitk checkpoint record-reclassification` — both are append-only, so the
  snapshot alone carries the full accepted-artifact and reclassification
  history across a resume, with no dependence on chat memory. Pair every
  `record-reclassification` call with an `observation` event (`kind:
  reclassify`) per `skills/metrics-emit` — the checkpoint record is the
  durable state, the observation is what lets `skills/reflection` notice the
  same classification going wrong more than once.
