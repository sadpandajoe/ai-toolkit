# Create Feature — Multi-Phase Path

Runs in place of every other path when `SKILL.md` step 2's Size Gate derives
`execution_shape: MULTI_PHASE`. Complexity (step 1) does not select a path
for the unit as a whole here — `decompose-work.md` reclassifies each phase
independently, and that phase's own classification picks its path.

**This path does not use `bin/aitk checkpoint advance()`.** That mechanism
resumes only through a fixed, pre-declared phase list keyed to a named
workflow contract in `interfaces/contracts.json` (e.g. its own legacy
`create-feature` contract there hardcodes `plan`/`implement`/`verify`/
`review`) — it has no way to accept the phase names `decompose-work.md`
derives at runtime for this specific feature. Cross-phase persistence here
is hand-set `PROJECT.md` frontmatter (same convention as the Size Gate
fields above) plus `aitk gate-state set` under a gate name scoped per phase
— never the checkpoint contract system, which stays reserved for the fixed
utility/legacy workflows that already declare their phases up front.

`decompose-work.md` and `plan-phase.md` each carry their own
`aitk-model-route` marker; this path calls them as procedures, so it
registers no new dispatch boundary of its own.

1. Run `skills/planning/references/decompose-work.md` once for the whole
   unit. Its `architecture_plan_status` must reach `PASS` before continuing
   — on `RECLASSIFY`/`ESCALATE`, stop and surface it rather than guessing a
   phase list. Persist its architecture artifact (boundaries, dependencies,
   global invariants, phase exit goals) as its own section in the durable
   plan artifact for this unit (`PLAN.md`, or a `PROJECT.md` body section if
   no `PLAN.md` was opened) — never inside the frontmatter fields below,
   which hold only the current phase's own classification.

2. For each phase, in the decomposition's declared order:
   a. Hand-set `current_phase` to that phase's name on `PROJECT.md`'s
      frontmatter — a short slug, matching the source plan's own example
      (`current_phase: layout-editing`).
   b. Reclassify complexity and size for this phase alone
      (`phase_complexity`, `phase_size`, `phase_execution_shape`, and — if
      needed — a fresh `phaseability_reason`) using `SKILL.md` steps 1–2
      above, scoped to this phase's work only. A phase that itself
      classifies `MULTI_PHASE` recurses into this same path one level down
      rather than being forced flat.
   c. Run `skills/planning/references/plan-phase.md` for this phase; its
      `phase_plan_status` must reach `PASS` before implementation starts.
      `plan-phase.md`'s own planning retry budget
      (`reasoning_attempts.phase_plan`) is independent from the gate-state
      repeat-failure count in step (e) below — do not conflate the two, and
      do not reset one when the other resets.
   d. Implement and verify this phase using whichever path its own
      `phase_execution_shape` selects from step (b) — `SKILL.md` steps 3–7
      for `SINGLE_PHASE`, the Complex Path's per-slice/wave loop for
      `BATCHED`, or a nested Multi-Phase Path for a rare nested
      `MULTI_PHASE` phase — reusing the same `create-feature.implement` /
      `create-feature.test-authoring` / `create-feature.review` boundaries;
      no new dispatch boundaries per phase.
   e. Verify the phase against gate name
      `create-feature-phase-<phase name>-verify` (substituting this phase's
      `current_phase` slug) via `skills/verification-loop/SKILL.md`, so
      `aitk.gates.decide_failure`'s repeat-failure counting stays scoped to
      this phase and does not bleed into the next one's history. Record the
      decided state via `aitk gate-state set` before moving on — this is the
      phase checkpoint: a fresh context resuming mid-unit reads
      `current_phase` plus this phase-scoped gate history to know exactly
      which phase is in flight and what it has already tried, with no need
      to replay the whole unit.
   f. On `PASS`, move to the next phase. On `RECLASSIFY`/`ESCALATE` from
      either the phase plan or its verification, stop and surface it — do
      not silently reorder or drop a phase from the decomposition.

3. Once every phase's gate reaches `PASS`, proceed to `SKILL.md` step 7
   (completion), recording the full phase history (every phase's gate
   outcome), not just the last phase's frontmatter fields.
