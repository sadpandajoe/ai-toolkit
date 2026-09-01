# Fix CI — Complex Path

Runs in place of the Trivial and Standard branches when `SKILL.md` step 6
routes here — because a single failure is genuinely ambiguous or
architectural, because step 3 grouped the run into more than one independent
root cause, or because step 5's `execution_shape` is `BATCHED`. Emit the
Phase Plan block per `rules/complexity-gate.md`'s Complex Path section
immediately after the Size Gate, before step 1 below. Its `Phases:` list
names this workflow's own execution units — implementation slices, or
waves/items for a `BATCHED` shape — never architecture-decomposition
phases; those belong only to `MULTI_PHASE`'s Multi-Phase Path.

<!-- aitk-model-route:fix-ci.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it step 3's grouped failure list as Goal. It returns a plan
   decomposed into the smallest implementable slices — one per independent
   root cause when the run has more than one, ordered smallest/safest first
   per `skills/debug/references/ci-fix-orchestration.md`'s Group failures
   rule — each with entrance/exit criteria and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   investigate, implement, and optional test-authoring steps (steps 1–3)
   against that unit's scope; then verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-ci-verify`,
   scoped to that unit — follow its RETRY/ESCALATE handling exactly, same
   as `SKILL.md` step 9; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 4). This reuses the `fix-ci.investigate`
   / `fix-ci.implement` / `fix-ci.test-authoring` / `fix-ci.review`
   boundaries above per unit — it is a loop over the same dispatch sites,
   not new ones. Move to the next unit only once this unit's review Gate
   block reaches `PASS`. For a `BATCHED` shape specifically, also run one
   final aggregate verification against gate name `fix-ci-verify` after the
   last wave/item, before step 10 — per-wave verification alone does not
   confirm the waves compose correctly together.

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-ci.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) — dispatch native
   `deep-rca-worker` when `routed_subagent` is native for the provider,
   otherwise the Codex `rca` contract via `model-run` — and check the
   result against `skills/debug/references/review-rca.md`'s RCA Gate
   Evidence Checklist before treating it as ready for implementation.

4. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 9 of `SKILL.md` does not run again once the Complex Path is
   running. Only proceed to step 10 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).
