# Debug Gotchas

Known traps for diagnosis and bug-fix workflows.

## Close Unsafe Behavior at the API Boundary

**Symptom:** A frontend performance or correctness bug is fixed only at the caller, while the backend endpoint still allows the unsafe request.

**Why:** Other callers, scripts, future UI changes, or integrations can hit the same unbounded, unvalidated, or incorrectly scoped endpoint later.

**Do instead:** When the client was doing something unsafe and the endpoint permitted it, ask whether the endpoint should enforce the safety property too:
- Missing pagination params -> default or cap page size server-side.
- Missing filters -> validate required scoping server-side.
- Unbounded batch size -> cap accepted batch sizes.

Record it under `Latent findings` in the RCA record; the plan includes it only if accepted.
