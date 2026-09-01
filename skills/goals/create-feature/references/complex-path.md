# Create Feature — Complex Path

Runs in place of the Trivial and Standard branches when `SKILL.md` step 3
routes here — for a `COMPLEX`/low-confidence `SINGLE_PHASE` unit, or for any
`BATCHED` unit regardless of complexity tier. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — implementation slices for a `SINGLE_PHASE` unit, or
waves/items for a `BATCHED` one — never architecture-decomposition phases;
those belong only to `MULTI_PHASE`'s Multi-Phase Path, via
`decompose-work.md`.

<!-- aitk-model-route:create-feature.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the feature request as Goal. It returns a plan
   decomposed into the smallest implementable slices, each with
   entrance/exit criteria and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   implement and optional test-authoring steps (steps 1–2) against that
   unit's scope; then verify it using `skills/verification-loop/SKILL.md`
   against gate name `create-feature-verify`, scoped to that unit — follow
   its RETRY/ESCALATE handling exactly, same as `SKILL.md` step 6; once that
   verification reaches `PASS`, dispatch the Standard Path's review step
   (step 3). This reuses the `create-feature.implement` /
   `create-feature.test-authoring` / `create-feature.review` boundaries
   above per unit — it is a loop over the same dispatch sites, not new ones.
   Move to the next unit only once this one's review Gate block reaches
   `PASS`. For a `BATCHED` shape specifically, also run one final aggregate
   verification against gate name `create-feature-verify` after the last
   wave/item, before step 7 — per-wave verification alone does not confirm
   the waves compose correctly together.

3. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 6 of `SKILL.md` does not run again once the Complex Path is
   running. Only proceed to step 7 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).
