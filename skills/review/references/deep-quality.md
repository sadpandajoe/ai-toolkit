# Deep Quality Review (Strict Structural Findings)

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Goal

Find the structural problems this change introduces or grows: what will make
the code harder to change next time. The independent reviewer already grades
routine duplication, reuse, placement, and test coverage; this lens goes
deeper on structure. Grade only in-scope findings, per Grading Calibration in
the code-review rule (scope before correctness, symmetry capped at `[minor]`).

What to look for:

- **Spaghetti growth.** Ad-hoc conditionals, one-off flags or modes, and
  special cases bolted into unrelated flows, or narrow edge handling dropped
  into an already busy function. `[major]` when an existing path becomes
  materially harder to reason about, `[minor]` when it only dents legibility.
- **Indirection without payoff.** Thin wrappers, identity abstractions,
  pass-through helpers, and generic "magic" mechanisms that hide a simple
  data-shape assumption. Usually `[minor]`.
- **Unclear boundaries.** Unnecessary optionality, `any`/`unknown`, cast-heavy
  code, or loosely shaped objects where an explicit typed model would do; a
  silent fallback that papers over an unclear invariant is `[minor]`, `[major]`
  when it can mask a real defect.
- **Leaking layers.** Feature logic in shared modules, implementation details
  exposed through APIs, and bespoke near-duplicates of a canonical utility.
  Routine duplication is graded by the code-review rule; raise it here only
  when the drift is architectural (`[major]`).
- **Orchestration.** Independent work serialized for no reason, or related
  updates that can leave state half-applied, when the cleaner structure is
  obvious (`[minor]`).
- **File size.** Graded once, in `rules/code-review.md` (Grading
  Calibration): `[minor]`, rising to `[major]` when the file was already over
  the limit and grew materially.

Report every structural finding you see, with your confidence when it is less
than high; the parent validates and ranks them. When a finding points at a
genuinely simpler design rather than a local fix, say so in one line;
proposing the restructuring is the code-judo lens's job. In `verification`,
list exactly what you read or ran.
