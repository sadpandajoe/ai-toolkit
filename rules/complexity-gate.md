# Complexity Gate

Classify before implementing, after enough read-only inspection to avoid
guessing. Persist the result immediately with `bin/aitk project-state init`
(or `set` on reclassification) so every later loop iteration reads it from
`PROJECT.md` instead of chat.

## Two Axes, One Shape

**Complexity** answers "how hard or risky is the reasoning?" and chooses the
reasoning tier.

| Level | Meaning | Default execution |
|---|---|---|
| `TRIVIAL` | Mechanical, obvious pattern, no design decision | Parent inline; smallest meaningful verification; review exception may apply |
| `STANDARD` | Real, contained engineering with a known pattern and bounded risk | Parent (or implementer worker) implements and tests; one independent review |
| `COMPLEX` | Meaningful architecture or RCA choice, broad risk, or several plausible paths | Feature: Opus plan, Sol validates, Sonnet implements. Bug: Sol RCA, Sonnet fixes. Then independent review |

STANDARD is the default for real work. Hard COMPLEX signals, any one of which
forces COMPLEX regardless of size: schema or migrations, auth/security/
permissions, public contracts, async or concurrency, caching, cross-service
behavior, backwards compatibility, a new architectural pattern.

**Size** answers "how much implementation surface is there?"

| Size | Meaning |
|---|---|
| `S` | One small coherent change |
| `M` | Several connected edits forming one unit |
| `L` | Broad surface; a phaseability check is required, and MULTI_PHASE is the expected answer |
| `XL` | Workstream-sized; MULTI_PHASE by default |

**Execution shape** is derived, never assumed. S and M are `SINGLE_PHASE` unless
independent behavioral phases are obvious. L runs the phaseability check and
leans `MULTI_PHASE`: independently verifiable units where finishing one changes
how the next is planned means `MULTI_PHASE`; the same mechanical operation
repeated many times means `BATCHED`; `SINGLE_PHASE` only when the check proves
the work has no independently verifiable unit, and that proof is the recorded
phaseability reason (the runtime refuses L or XL with `none` and no reason). XL
is `MULTI_PHASE` unless it is a mechanical codemod, which is `BATCHED`. Size
never implies complexity: an 80-file rename is STANDARD/XL/BATCHED; a one-line
permission toggle is COMPLEX/S.

Each MULTI_PHASE phase is classified on its own; a COMPLEX project usually has
mostly STANDARD phases.

## Reclassification

Escalate when new evidence invalidates an assumption; never silently downgrade.
Record it as a `RECLASSIFY` gate with the evidence, update the snapshot, and
re-enter the loop. Two failed implementation attempts, a materially changed
RCA, or a hard signal discovered mid-work are reclassification triggers.

## Block Shape

```markdown
## Complexity Gate
Complexity: TRIVIAL | STANDARD | COMPLEX
Size: S | M | L | XL
Shape: SINGLE_PHASE | BATCHED | MULTI_PHASE — <phaseability reason, or "S/M default">
Confidence: HIGH | MEDIUM | LOW
Modifiers: <hard signals, or none>
Reason: <one line>
```

Always emit the block; a silent path choice is a defect. Workflow-specific
signal tables live in the workflow reference, not here.
