# Complexity Gate

Classification protocol for workflows that branch on trivial, standard, or
complex paths. This defines the output block format and path rules. Signal
tables stay in the canonical workflow reference.

## Block Format

Always emit this block in conversation before branching:

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Certainty: Clear / Uncertain
Reason: [one line]
```

`Certainty` replaces a numeric confidence score. A scalar invited false
precision — arguing 7 versus 8 is not a judgment the classification actually
needs. The question that matters is binary: is there real doubt about this
classification, yes or no?

- **Clear** — the classification signals line up; no material doubt remains.
- **Uncertain** — any real doubt about scope, root cause, or blast radius.
  **Uncertain always reclassifies one tier up rather than forcing a fast path
  through doubt**: `TRIVIAL` + Uncertain becomes `STANDARD`; `STANDARD` +
  Uncertain becomes `COMPLEX`. Escalate the tier, don't lower the bar for it.

## Size and Shape Gate

This classification pairs with a second gate — size (`S`/`M`/`L`/`XL`) and
the `execution_shape` it derives (`SINGLE_PHASE`/`BATCHED`/`MULTI_PHASE`),
per `aitk/size_axis.py`. The canonical block shape, phaseability signal
table, and derivation rules are defined once, in
`skills/goals/create-feature/SKILL.md`'s Size Gate step — `fix-bug`,
`fix-ci`, and `refactor` all point there rather than duplicating it. This
rule does not restate that table; read it there.

## Trivial Fast-Path

When classification is `TRIVIAL` and certainty is `Clear`:
- **Auto-proceed** — do not ask the user for confirmation before implementing; the clear classification is the approval
- Skip the formal planning phase, investigation lanes, and RCA validation
- Go directly to implementation, verification, `rules/gates.md` Gate block emission, and summary
- A skipped or micro-fix-only review is `PASS` with the skip reason recorded in `Reason`, per `rules/gates.md`; if the change actually needs logic review, reclassify STANDARD instead of skipping it
- Zero subagent spawns **for the implementation path** — the orchestrator scopes, implements, and verifies inline

**Scope of the zero-spawn rule.** It governs the implementation path only. A
workflow whose *product* is a review — `review-code`, `review-pr`,
`review-code-adversarial` — still runs exactly one fresh reviewer at TRIVIAL:
the never-review-your-own-work rule outranks the fast path, and one lane is the
floor, not zero. That single lane *is* the independent review; TRIVIAL does not
add a second-opinion lane on top of it. An explicit deep review pins the tier to
at least COMPLEX, so it never takes this path at all.

## Standard Path

When classification is `STANDARD` and certainty is `Clear`:
- Skip the formal planning phase and parallel investigation-lane subagents
- Orchestrator scopes, investigates, or plans inline as the workflow requires
- Still run one workflow-required review phase with at least one fresh reviewer — never review your own work. Review workflows may launch all triggered lanes for the diff; feature work usually runs code review after implementation. Run plan review only when inline design uncovered real design uncertainty.
- Still run tests and emit a `rules/gates.md` Gate block for the review checkpoint
- Spawn additional subagents only when parallelism provides a clear wall-clock win

**When to classify STANDARD** (any of these signals):
- 2–4 files touched, but within a single subsystem
- Non-mechanical change, but well-understood pattern (add endpoint, extend model, new test file)
- No architectural decisions or cross-system trade-offs
- Clear fix or implementation approach — investigation confirms rather than discovers

STANDARD is the **default classification** — most real work lands here. Use TRIVIAL only for truly mechanical changes, COMPLEX only when genuine multi-system complexity or ambiguity exists.

## Complex Path

When classification is `COMPLEX` (or certainty is `Uncertain` for any classification):
- Full workflow: durable plan or investigation artifact as the command requires, reviewer subagents, and validation gates
- Use `fresh_subagent`/`parallel_fanout` only where the workflow and
  `rules/orchestration.md` reasoning-load boundaries call for them.
- **Emit a Phase Plan block immediately after the Complexity Gate** (see below). This announces the cadence — including planned checkpoint boundaries — upfront, before the first phase starts.

## Phase Plan Block (COMPLEX only)

After emitting the Complexity Gate, emit a Phase Plan that names the remaining phases and where checkpoints will fire. This makes the cadence predictable to the user instead of firing silently mid-workflow. Each phase is its own isolation boundary by dispatch — a worker per phase per `rules/context-management.md`'s Workers as Phase Isolation — not by an explicit clear the orchestrator has to trigger.

Format:

```markdown
## Phase Plan
Phases: [phase 1] → [checkpoint] → [phase 2] → [checkpoint] → ... → [final phase]
Checkpoints fire after: [list of durable artifacts that trigger a checkpoint]
Resume contract: PROJECT.md (+ manifest if any) carries state across any reset — worker dispatch, provider auto-compact, or a fresh session alike.
```

Pull the phase list from the selected workflow's COMPLEX happy path. Pull the
checkpoint list from its contract and `rules/context-management.md`'s No
Explicit-Reset Dependency section. This rule owns the block shape only; it must not
copy workflow-specific phase sequences.

If the user's request is genuinely too small for COMPLEX (≤2 phases after Complexity Gate), reclassify STANDARD rather than emit a degenerate Phase Plan.

## Modifiers

When the request or `PROJECT.md`'s frontmatter `modifiers` list contains
`hotfix` or `p1`, apply these overrides on top of whatever tier steps 1-2
land on:

- **(a) Floor at STANDARD** — never classify below `STANDARD`, even if the
  change would otherwise read as `TRIVIAL`.
- **(b) Review required before publish** — the review pass (per
  `rules/gates.md`) must reach `PASS` before any push, PR, or release step.
- **(c) Review moves earlier** — pull the independent review in right after
  the first implementation slice instead of waiting for the last one.
- **(d) Tighter reasoning budget** — override `rules/gates.md`'s
  Repeat-Failure Counting Rule for this workflow: skip the informed retry and
  `ESCALATE` on the first reasoning failure at any gate.

## Never Silently Decide

Always emit the gate block above. Do not silently choose a path — the block must be visible in conversation so the user and any continuation checkpoint can see the classification. COMPLEX work must additionally emit the Phase Plan block; a silent COMPLEX path is a defect.

## Worked Examples

### TRIVIAL

- **Typo in error message**: 1 file, no logic change, no regression risk. Certainty: Clear.
- **Config value change**: 1-2 files, mechanical substitution, testable in isolation. Certainty: Clear.
- **Missing import after rename**: 1 file, fix is deterministic from the error, no design decision. Certainty: Clear.

### STANDARD

- **Add a small setting to an existing panel**: 2-4 files in one UI subsystem, known pattern, contained user-visible behavior. Certainty: Clear.
- **Extend an existing API response with tests**: handler/model/test change in one subsystem, no new contract shape beyond one field. Certainty: Clear.
- **Add one known-pattern validation path**: existing validator and targeted tests, clear error behavior, no adjacent workflow redesign. Certainty: Clear.

### COMPLEX

- **New export flow across UI and API**: 3+ files, acceptance criteria need a durable plan, and tests/validation span layers. Certainty: Uncertain until planned.
- **Permission-sensitive bulk action**: Cross-cutting impact across UI, backend, authz, and audit paths. Certainty: Uncertain until scoped.
- **Feature flag behavior changes an existing workflow**: Multiple adjacent flows may regress; needs plan-review iteration or multiple review/fix waves and validation. Certainty: Uncertain.
- **Bug fix with unclear root cause**: request flow or data path is not yet understood; needs investigation and RCA validation. Certainty: Uncertain until investigated.

## Scope

This rule defines an output contract. It does not define signal tables or
path-specific steps; those are owned by canonical workflow references.
