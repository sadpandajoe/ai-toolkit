# Testing

## Golden Rules

- **Evidence before completion.** A change is done when the check that proves it
  ran and passed, and the result is quoted. Inspection is not evidence.
- **Test behavior, not implementation.** Tests survive refactors.
- **Regression evidence for bugs.** The test fails before the fix and passes
  after when feasible; record why when it is not.
- **Fixtures, not hard-coded data. Mock only external boundaries**: APIs,
  databases, filesystem, network, time.
- **One assertion concept per test. Fix failing tests immediately.**
- **Fix the invariant, not the test.** When a test is red or proposed for
  deletion to fit broken-but-current behavior, fix the behavior. Loosen or delete
  only when the test itself is wrong (asserts an unintended side effect, depends
  on a removed feature, encodes a judgment nobody stands by).
- **Delete tests for deleted features. Follow project conventions.**
- **Escalate test strategy only when it is ambiguous.** Routine test authoring
  is the implementer's or tester's job; a specialist answers "does this test
  prove the right thing?", not "write the tests".

## Layers and Mocks

| Layer | When | Mock |
|---|---|---|
| Unit | Pure logic | No |
| Integration | Crosses an external boundary | The boundary |
| E2E | Full user workflow | No |

Over-mocking signals: setup longer than the test, removing the code under test
does not break it, the test verifies mock pass-through, mocks of internal
functions, or mocks of fast deterministic code. Reduce mocks and test real code.

## Common Issues

Flaky means timing: use proper waits. False positives mean over-mocking. Breaks
on refactor means implementation testing. A slow suite means too much E2E; push
down a layer.
