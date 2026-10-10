# Implementation Review

The feasibility checklist the plan validator applies in `phase-plan` and
`fix-plan` modes. It adds what to check; how to grade and report comes from the
validator contract.

Read before grading: `rules/severity.md`

- **Sequencing.** Dependencies between slices or phases are respected, and
  each phase is small enough to review and safe to deploy on its own.
- **Dependencies exist.** Every library, API, file, and symbol the plan relies
  on exists in the repo or is explicitly new.
- **Migrations.** A migration ships with the code that uses it, not ahead of it
  in its own PR (if a lone migration has to be reverted, the code that depends
  on it may already be deployed), and the plan covers backward compatibility,
  data migration, and rollback.
- **Vertical slices.** Phases deliver end-to-end slices rather than horizontal
  layers (all models, then all APIs, then all UI), so each one is testable and
  leaves the system working.
- **Risk.** For each step, what is most likely to go wrong, and whether the
  plan says what happens then.
- **Consistency.** The approach follows the codebase's existing patterns; find
  them in the repo rather than assuming.

Architecture, test-strategy detail, UI design, and code style belong to the
other parts of the validator's focus.
