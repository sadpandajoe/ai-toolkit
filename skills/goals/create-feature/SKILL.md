---
name: create-feature
description: Use when the user asks to build, add, or implement a new feature or capability. Covers the size-S SINGLE_PHASE happy path (S-size classification, any complexity tier) under rules/complexity-gate.md and aitk/size_axis.py. Do NOT use for bug fixes (skills/goals/fix-bug) or for M/L/XL-size feature work — that path is not wired here yet.
---

# Create Feature

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, and
`rules/specialist-handoff.md` first — they define the classification block,
the fast-path rules, the six-state gate contract, and the input/output shape
for every specialist dispatch this skill uses. This skill is the v2
goal-skill entry point for new-feature requests, implementing the S-size
`SINGLE_PHASE` happy path only.

## Scope

**In scope:** classify complexity (`rules/complexity-gate.md`) and size
(`aitk/size_axis.py`'s `S`/`M`/`L`/`XL`) for a feature request; when size
classifies `S` — which always derives `execution_shape: SINGLE_PHASE` — plan
just-in-time and implement via the Trivial/Standard/Complex path per
`rules/complexity-gate.md`, the same structure `skills/goals/fix-bug` uses
for bug fixes; verify and record completion.

**Out of scope (this commit):** `M`/`L`/`XL` sizes and the `BATCHED`/
`MULTI_PHASE` execution shapes those can derive. That path routes through
`skills/planning/references/decompose-work.md` and `plan-phase.md` and lands
in a later commit — this skeleton does not attempt it. If size classifies as
anything but `S`, stop after step 2 below and tell the user this skill's
larger-feature path isn't wired yet, rather than guessing at a plan.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Confidence: X/10
   Reason: [one line]
   ```
2. Emit a Size Gate block, classifying against `aitk/size_axis.py`'s `size`
   enum and deriving `execution_shape` per the source plan's sizing table
   (`S`/`M` default `SINGLE_PHASE`; `L` needs a phaseability check; `XL`
   defaults `MULTI_PHASE`):
   ```markdown
   ## Size Gate
   Size: S / M / L / XL
   Execution shape: SINGLE_PHASE / BATCHED / MULTI_PHASE
   Reason: [one line]
   ```
   Persist `size`, `execution_shape`, and (if not obviously `SINGLE_PHASE`)
   `phaseability_reason` directly on `PROJECT.md`'s frontmatter — these
   fields are hand-set classification state, the same way `workflow` and
   `complexity` already are; `aitk/size_axis.py` validates the shape, it does
   not own writing it. If `Size` is anything but `S`, stop here per the
   Scope section above instead of continuing to step 3.
3. If the classification from step 1 is `COMPLEX`, or confidence is below
   `8/10` at any tier: follow the Complex Path below instead of implementing
   inline or using the Standard Path.
4. If `TRIVIAL` at `8/10` confidence or higher: implement the feature
   inline, per the Trivial Fast-Path rules in `rules/complexity-gate.md` — no
   subagent spawns for the implementation itself, no formal planning phase.
   Skip to step 6.
5. If `STANDARD` at `8/10` confidence or higher, follow the Standard Path
   below instead of implementing inline.
6. For `TRIVIAL` and `STANDARD` only: verify using
   `skills/verification-loop/SKILL.md` against gate name
   `create-feature-verify`. Follow its RETRY/ESCALATE handling exactly — one
   fix attempt on `RETRY`, stop and surface to the user on `ESCALATE`.
   `COMPLEX` skips this step — the Complex Path verifies per slice and goes
   straight to step 7.
7. On `PASS`: record a completion entry on `PROJECT.md` (including the size
   fields set at step 2) and summarize the feature for the user. A `PASS`
   gate is a checkpoint, not license to stop before this step — see
   `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 5 and 6 above, in place of inline implementation. Unlike
`fix-bug`, there is no root-cause investigation phase — a feature request
starts from what the user described, not a symptom. Survey existing patterns
to follow inline, as the orchestrator (`rules/complexity-gate.md`'s Standard
Path already allows inline investigation/planning at this tier); no
specialist dispatch for the survey itself.

<!-- aitk-model-route:create-feature.implement -->
1. Dispatch `implementation-worker` per `rules/specialist-handoff.md` (Phase:
   implement), handing it the feature request, the surveyed pattern to
   follow, and a Scope naming the files it may touch. It writes tests first
   per `rules/implementation.md`'s Test-First Modes, then the feature code.

<!-- aitk-model-route:create-feature.test-authoring -->
2. Dispatch `test-worker` separately only when the feature needs coverage
   beyond the implementation worker's own tests (e.g. a new integration
   surface) — not on every `STANDARD` feature.

<!-- aitk-model-route:create-feature.review -->
3. After verification (step 6) reaches `PASS`, dispatch one fresh reviewer
   via the `review` route (`rules/model-assignment.md`) against the
   resulting diff — never the worker that implemented the feature; never
   review your own work. Translate its findings into a `rules/gates.md` Gate
   block using the Mapping From the Old Mechanisms section: clean or
   micro-fix-only findings → `PASS`; a fixable finding → `RETRY`; the same
   finding recurring after a fix attempt → `ESCALATE`; an unresolved
   required finding with no ambiguity → `BLOCKED`; a genuine trade-off →
   `USER_DECISION`.

4. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here.
Emit the Phase Plan block per `rules/complexity-gate.md`'s Complex Path
section immediately after the Size Gate, before step 1 below. Its `Phases:`
list names this workflow's own phases (plan → per-slice implementation loop
→ completion) — never architecture-decomposition phases, since size `S`
always stays `SINGLE_PHASE` and never reaches `decompose-work.md`.

<!-- aitk-model-route:create-feature.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the feature request as Goal. It returns a plan
   decomposed into the smallest implementable slices, each with
   entrance/exit criteria and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice, in order: dispatch the Standard Path's implement and
   optional test-authoring steps (steps 1–2) against that slice's scope;
   then verify the slice using `skills/verification-loop/SKILL.md` against
   gate name `create-feature-verify`, scoped to that slice — follow its
   RETRY/ESCALATE handling exactly, same as step 6 above; once that
   verification reaches `PASS`, dispatch the Standard Path's review step
   (step 3). This reuses the `create-feature.implement` /
   `create-feature.test-authoring` / `create-feature.review` boundaries
   above per slice — it is a loop over the same dispatch sites, not new
   ones. Move to the next slice only once this slice's review Gate block
   reaches `PASS`.

3. Every slice verifies and reviews within its own iteration of step 2 —
   step 6 above does not run again for `COMPLEX`. Only proceed to step 7
   (completion) once every slice's review Gate block reaches `PASS`.

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Confidence: X/10
Reason: [one line]
```
followed by the Size Gate block, the Phase Plan block (`COMPLEX` only), the
`verification-loop` Gate block (every path), the review Gate block
(`STANDARD` and `COMPLEX`), then a short summary of the feature once every
gate reaches `PASS`.

## Notes

- This skill is dual-run alongside
  `skills/workflows/references/create-feature.md` today; nothing dispatches
  "create feature" requests here yet. The dual-run router pointer that makes
  this skill a live dispatch target lands in a later commit, same as
  `fix-bug`'s C30. Reading and testing it does not change live behavior.
- `M`/`L`/`XL` sizes, and the `MULTI_PHASE`/`BATCHED` execution shapes they
  can derive, land in a later commit — that path threads
  `skills/planning/references/decompose-work.md` and `plan-phase.md` into
  this skill's Complex Path in place of the single-slice loop above.
