# Durable Workflow Runtime

For every workflow whose manifest `execution_class` is `durable`, treat its
entry in `interfaces/contracts.json` as the machine-readable phase,
authorization, effect, verification, and reporting contract, and the routing
snapshot in `PROJECT.md` as the authoritative resume state.

- Record classification first with `bin/aitk project-state init --workflow
  <name> --complexity ... --size ...`; record every gate outcome with
  `bin/aitk project-state gate` and every phase move with `bin/aitk
  project-state advance`. Resume from the snapshot's phase and gate, never from
  chat history.
- Initialize the live artifact with `bin/aitk checkpoint init --workflow
  <name>` and validate it before resuming. Re-running init for the same valid
  workflow is a no-op so it cannot erase progress. Starting a different run
  requires `--replace`; replacement refuses while any effect is pending. Never
  hand-edit the delimited machine blocks or use the repository template as live
  state.
- Advance only through declared phase edges with `bin/aitk checkpoint advance`.
  Persist the human-readable state required by the workflow before advancing.
- Complete the contract's authorization and preflight gates before any effect.
  A failed gate stops the workflow with no reservation or effect.
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
