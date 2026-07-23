# Complexity Gate

Classification protocol for workflows that branch on trivial, moderate, or
standard paths. This defines the output block format and path rules. Signal
tables stay in the canonical workflow reference.

## Block Format

Always emit this block in conversation before branching:

```markdown
## Complexity Gate
Classification: TRIVIAL / MODERATE / STANDARD
Confidence: X/10
Reason: [one line]
```

## Trivial Fast-Path

When classification is `TRIVIAL` and confidence is `8/10` or higher:
- **Auto-proceed** — do not ask the user for confirmation before implementing; the high-confidence classification is the approval
- Skip the formal planning phase, investigation lanes, RCA validation, and reviewer subagents
- Go directly to implementation, verification, Review Gate emission, and summary
- Emit Review Gate `skipped` or `micro-fix` only when `rules/review-gate.md` allows it; otherwise reclassify as MODERATE before logic review
- Zero subagent spawns — orchestrator does all work inline

## Moderate Path

When classification is `MODERATE` and confidence is `8/10` or higher:
- Skip the formal planning phase and parallel investigation-lane subagents
- Orchestrator scopes, investigates, or plans inline as the workflow requires
- Still run one workflow-required review phase with at least one fresh reviewer — never review your own work. Review workflows may launch all triggered lanes for the diff; feature work usually runs code review after implementation. Run plan review only when inline design uncovered real design uncertainty.
- Still run tests and emit a Review Gate block
- Spawn additional subagents only when parallelism provides a clear wall-clock win

**When to classify MODERATE** (any of these signals):
- 2–4 files touched, but within a single subsystem
- Non-mechanical change, but well-understood pattern (add endpoint, extend model, new test file)
- No architectural decisions or cross-system trade-offs
- Clear fix or implementation approach — investigation confirms rather than discovers

MODERATE is the **default classification** — most real work lands here. Use TRIVIAL only for truly mechanical changes, STANDARD only when genuine multi-system complexity or ambiguity exists.

## Standard Path

When classification is `STANDARD` (or confidence is below `8/10` for any classification):
- Full workflow: durable plan or investigation artifact as the command requires, reviewer subagents, and validation gates
- Use `fresh_subagent`/`parallel_fanout` only where the workflow and
  `rules/orchestration.md` reasoning-load boundaries call for them.
- **Emit a Phase Plan block immediately after the Complexity Gate** (see below). This announces the cadence — including planned checkpoint/context-reset boundaries — upfront, before the first phase starts.

## Phase Plan Block (STANDARD only)

After emitting the Complexity Gate, emit a Phase Plan that names the remaining phases and where checkpoint/context-reset will fire. This makes context cadence predictable to the user instead of firing silently mid-workflow.

Format:

```markdown
## Phase Plan
Phases: [phase 1] → [clear] → [phase 2] → [clear] → ... → [final phase]
Checkpoints fire after: [list of durable artifacts that trigger checkpoint + context_reset]
Resume contract: PROJECT.md (+ manifest if any) carries state across clears.
```

Pull the phase list from the selected workflow's STANDARD happy path. Pull the
checkpoint/reset list from its contract and `rules/context-management.md`
Proactive Phase Reset Policy. This rule owns the block shape only; it must not
copy workflow-specific phase sequences.

If the user's request is genuinely too small for STANDARD (≤2 phases after Complexity Gate), reclassify MODERATE rather than emit a degenerate Phase Plan.

## Never Silently Decide

Always emit the gate block above. Do not silently choose a path — the block must be visible in conversation so the user and any continuation checkpoint can see the classification. STANDARD work must additionally emit the Phase Plan block; a silent STANDARD path is a defect.

## Worked Examples

### TRIVIAL

- **Typo in error message**: 1 file, no logic change, no regression risk. Confidence 10/10.
- **Config value change**: 1-2 files, mechanical substitution, testable in isolation. Confidence 9/10.
- **Missing import after rename**: 1 file, fix is deterministic from the error, no design decision. Confidence 9/10.

### MODERATE

- **Add a small setting to an existing panel**: 2-4 files in one UI subsystem, known pattern, contained user-visible behavior. Confidence 8/10.
- **Extend an existing API response with tests**: handler/model/test change in one subsystem, no new contract shape beyond one field. Confidence 8/10.
- **Add one known-pattern validation path**: existing validator and targeted tests, clear error behavior, no adjacent workflow redesign. Confidence 8/10.

### STANDARD

- **New export flow across UI and API**: 3+ files, acceptance criteria need a durable plan, and tests/validation span layers. Confidence 7/10 until planned.
- **Permission-sensitive bulk action**: Cross-cutting impact across UI, backend, authz, and audit paths. Confidence 6/10 until scoped.
- **Feature flag behavior changes an existing workflow**: Multiple adjacent flows may regress; needs plan-review iteration or multiple review/fix waves and validation. Confidence 7/10.
- **Bug fix with unclear root cause**: request flow or data path is not yet understood; needs investigation and RCA validation. Confidence 6/10 until investigated.

## Scope

This rule defines an output contract. It does not define signal tables or
path-specific steps; those are owned by canonical workflow references.
