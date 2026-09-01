# Fix Bug — Multi-Phase Path

Runs in place of every other path when `SKILL.md` step 2's Size Gate derives
`execution_shape: MULTI_PHASE` — a bug whose root cause and fix genuinely
decompose into distinct, independently-verifiable repairs. Mirrors
`skills/goals/create-feature/SKILL.md`'s Multi-Phase Path exactly,
substituting this skill's own dispatch boundaries and gate names:

1. Run `skills/planning/references/decompose-work.md` once for the whole bug.
   Its `architecture_plan_status` must reach `PASS` before continuing — on
   `RECLASSIFY`/`ESCALATE`, stop and surface it rather than guessing a phase
   list. Persist its architecture artifact per `create-feature`'s Multi-Phase
   Path step 1.

2. For each phase, in the decomposition's declared order, following
   `create-feature`'s Multi-Phase Path step 2 (a)–(f) exactly: hand-set
   `current_phase`; reclassify `phase_complexity`/`phase_size`/
   `phase_execution_shape` for that phase alone; run `plan-phase.md` to
   `phase_plan_status: PASS`; implement and verify via whichever path the
   phase's own `phase_execution_shape` selects — reusing
   `fix-bug.investigate` / `fix-bug.implement` / `fix-bug.test-authoring` /
   `fix-bug.review`, including the Standard Path's RCA gate for any phase
   that runs it — and verify against gate name
   `fix-bug-phase-<phase name>-verify`. On `RECLASSIFY`/`ESCALATE`, stop and
   surface rather than silently reordering phases.

3. Once every phase's gate reaches `PASS`, proceed to `SKILL.md` step 7
   (completion), recording the full phase history.
