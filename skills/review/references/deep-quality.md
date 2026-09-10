---
tier: Heavy
---

# Deep Quality Review (Strict Structural Findings)

A strict maintainability **findings** lens: the concrete, pattern-matchable half
of a deep structural review. It runs as a conditional deep lens beside the
independent reviewer, which owns the baseline DRY, reuse, placement, and
test-coverage checks; this lens adds strict structural findings on
`deep-review`.

Its generative sibling, `references/code-judo.md`, *proposes*
behavior-preserving restructurings and returns unscored proposals at its own
boundary. The difference is output, not model.

## Triggers

`classify-diff` owns the trigger predicate (refactor shape, a "deep quality"
ask, or deep-tier escalation). This lens activates when the classifier lists it
under `Deep lenses`, and never re-derives the conditions. A bare "deep quality"
ask fires this lens only; it is not a deep-tier escalation.

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Standards

1. **File-size gate.** A diff that pushes a file across 1000 lines — from under
   1000 to over, or already over 1000 and grown materially by the diff — is a
   `[major]` structural smell by default; ask whether it should be decomposed
   first (extract helpers/subcomponents/modules). Waive only for a compelling
   structural reason where the result is still clearly organized.
2. **No spaghetti growth.** New ad-hoc conditionals, scattered special cases, or
   one-off branches bolted into unrelated flows are a design problem, not a
   style nit — `[major]` when they make an existing path materially harder to
   reason about, `[minor]` when they only dent legibility. Prefer pushing logic
   into a dedicated helper, state model, policy object, or module.
3. **Direct over magical.** Brittle, ad-hoc, or "magic" behavior is a
   code-quality problem. Be skeptical of generic mechanisms that hide simple
   data-shape assumptions. Flag thin wrappers, identity abstractions, and
   pass-through helpers that add indirection without buying clarity — `[minor]`.
4. **Type and boundary cleanliness.** Question unnecessary optionality,
   `any`/`unknown`, or cast-heavy code where a clearer type boundary could
   exist. Prefer explicit typed models over loosely-shaped ad-hoc objects. If a
   branch relies on silent fallback to paper over an unclear invariant, ask for
   the boundary to be made explicit — `[minor]`, `[major]` when the fallback can
   mask a real defect.
5. **Canonical layer + reuse.** Call out feature logic leaking into shared paths
   or implementation details leaking through APIs, and bespoke near-duplicates
   of an existing canonical utility. This overlaps the baseline DRY check in
   `rules/code-review.md` — grade routine duplication there, escalate here only
   when the drift is architectural (`[major]`).
6. **Orchestration / atomicity.** Flag independent work serialized for no reason,
   and related updates that can leave state half-applied, when the cleaner
   structure is obvious — `[minor]`. Do not over-index on micro-optimizations.

## What to Flag

- A file crossing 1000 lines due to the diff, or already over 1000 and
  materially grown by it, especially when the new code could be split out.
- New conditionals bolted onto unrelated code paths; one-off booleans/flags/modes
  that complicate existing control flow.
- Feature-specific logic leaking into general-purpose modules.
- Generic "magic" handling that hides simple structure; thin or identity
  wrappers that add indirection without simplifying anything.
- Unnecessary casts, `any`, `unknown`, or optional params that muddy the real
  contract.
- Copy-pasted logic instead of an extracted helper; bespoke helpers where a
  canonical utility already exists.
- Narrow edge-case handling implemented in the middle of an already busy
  function.
- Sequential async flow or partial-update logic where the cleaner structure is
  obvious.

When a finding points at a genuinely simpler *design* (not just a local fix),
note that the `code-judo` pass should propose the restructuring — do not attempt
the full reframing here; that is the generative lens's job.

## Output Ordering

Prioritize: (1) structural regressions, (2) spaghetti / branching-complexity
increases, (3) boundary / abstraction / type-contract problems, (4) file-size and
decomposition concerns, (5) modularity and abstraction issues, (6) legibility.

Prefer a small number of high-conviction findings over a long list of cosmetic
notes. Do not flood the review with nits when larger structural issues exist.

## Stop Rules

Apply the retry budget in `rules/gates.md`. Grade only in-scope findings per the
`rules/code-review.md` Finding Calibration (scope-before-correctness, symmetry
cap at `[minor]`).
