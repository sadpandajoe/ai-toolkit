# Fix CI — Multi-Phase Path

Runs in place of every other path when `SKILL.md` step 5's Size Gate derives
`execution_shape: MULTI_PHASE` — a CI failure whose fix genuinely requires
phased, architectural changes rather than several independent repairs.
Mirrors `skills/goals/create-feature/SKILL.md`'s Multi-Phase Path exactly,
substituting this skill's own dispatch boundaries and gate names:

1. Run `skills/planning/references/decompose-work.md` once for the whole
   failure. Its `architecture_plan_status` must reach `PASS` before
   continuing — on `RECLASSIFY`/`ESCALATE`, stop and surface it rather than
   guessing a phase list. Persist its architecture artifact per
   `create-feature`'s Multi-Phase Path step 1.

2. For each phase, in the decomposition's declared order, following
   `create-feature`'s Multi-Phase Path step 2 (a)–(f) exactly: hand-set
   `current_phase`; reclassify `phase_complexity`/`phase_size`/
   `phase_execution_shape` for that phase alone; run `plan-phase.md` to
   `phase_plan_status: PASS`; implement and verify via whichever path the
   phase's own `phase_execution_shape` selects — reusing
   `fix-ci.investigate` / `fix-ci.implement` / `fix-ci.test-authoring` /
   `fix-ci.review` — and verify against gate name
   `fix-ci-phase-<phase name>-verify`. On `RECLASSIFY`/`ESCALATE`, stop and
   surface rather than silently reordering phases.

3. Once every phase's gate reaches `PASS`, proceed to `SKILL.md` step 10
   (completion), recording the full phase history.
