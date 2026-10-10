# Test Plan Review

The test-strategy checklist the plan validator applies whenever a plan names
tests, and that `run-test-plan` uses to review its scenario matrix. It adds
what to check; how to grade and report comes from the validator contract.

Read before grading: `rules/severity.md`

- **Coverage.** What the plan tests and what it leaves untested, measured
  against the behavior change.
- **Layers.** Each behavior is tested at the lowest layer that can prove it,
  with integration or end-to-end tests only where the behavior crosses a
  boundary.
- **Edge and error paths.** Boundary conditions and failure paths are named,
  not implied.
- **Testable boundaries.** The design exposes interfaces a test can drive
  without reaching into internals.
- **Mocks and data.** Mocks sit only at external boundaries, and test data is
  managed and reproducible.
- **CI.** The tests will run reliably in CI: no dependence on local state,
  ordering, or wall-clock timing.

Architecture, code style, UI design, and sequencing belong to the other parts
of the validator's focus.
