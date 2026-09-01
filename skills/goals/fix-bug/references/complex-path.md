# Fix Bug — Complex Path

Runs in place of the Trivial and Standard branches when `SKILL.md` step 3
routes here — for a `COMPLEX`/low-confidence `SINGLE_PHASE` bug, or for any
`BATCHED` shape regardless of complexity tier. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — implementation slices for a `SINGLE_PHASE` bug, or
waves/items for a `BATCHED` one — never architecture-decomposition phases;
those belong only to `MULTI_PHASE`'s Multi-Phase Path.

<!-- aitk-model-route:fix-bug.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the bug report as Goal. It returns a plan decomposed
   into the smallest implementable slices, each with entrance/exit criteria
   and a scope boundary, per `skills/implement-change/SKILL.md`'s Slice
   Awareness section. Never implement from an unreviewed plan the planner
   itself approved — the planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   investigate, RCA-gate, implement, and optional test-authoring steps
   (steps 1–4) against that unit's scope; then verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-bug-verify`,
   scoped to that unit — follow its RETRY/ESCALATE handling exactly, same
   as `SKILL.md` step 6; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 5). This reuses the `fix-bug.investigate`
   / `fix-bug.implement` / `fix-bug.test-authoring` / `fix-bug.review`
   boundaries above per unit — it is a loop over the same dispatch sites,
   not new ones. Move to the next unit only once this unit's review Gate
   block reaches `PASS`. For a `BATCHED` shape specifically, follow
   `skills/verification-loop/SKILL.md`'s BATCHED shape subsection: after the
   last wave/item, before step 7, run the AGGREGATE verification against its
   own gate name (`fix-bug-verify-aggregate`, never reusing a wave's
   `fix-bug-verify` history).

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-bug.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) — dispatch native
   `deep-rca-worker` when `routed_subagent` is native for the provider,
   otherwise the Codex `rca` contract via `model-run` — before running
   step 2's RCA gate against `skills/debug/references/review-rca.md`'s
   checklist.

4. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 6 of `SKILL.md` does not run again once the Complex Path is
   running. Only proceed to step 7 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).
