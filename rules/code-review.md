# Code Review

## Core Principles

- **Consistency and modeling**: follow neighboring patterns; logic lives where a
  future reader would look; signatures match neighbors.
- **Tests must be able to fail**: always-green tests are noise; data matches
  types. Each new test fails when the behaviour it covers breaks, and the
  review says how. No mocks of internal code: mock only external boundaries
  (network, database, filesystem, time).

## Severity

Tags and definitions are in `rules/severity.md`. Calibrate missing-test
findings by what changed:

| Change | Missing tests | Severity |
|---|---|---|
| New public logic, new endpoint, bug fix, behavioral change | none | `[major]` |
| Config, flag, env var | none | `[minor]` |
| Docs, comments, types, renames, moves, formatting | none | not a finding |

**Name the locking assertion.** A missing-test finding states the assertion that
fails on today's code and passes once the change is correct. A finding whose
assertion cannot be named is either an unobservable behavior (the more serious
finding, say so) or a structure preference capped at `[nitpick]`.

CORE impact (login, auth, payment, data loss) shifts missing-test findings up
one level.

## Grading Calibration

This section and Severity above are the one home of finding calibration;
lens contracts point here.

- **Scope is upstream of correctness.** Confirm the `file:line` is in the diff
  before grading. Unchanged code goes to Remaining, not findings.
- **The diff is the recorded base to HEAD in every round.** Never re-derive
  scope from the last fix delta; a defect the review itself introduced in round
  one must still be reportable in round two.
- **Symmetry findings cap at `[minor]`**, with one exemption: a defect class
  confirmed inside this branch is graded on its own severity wherever it
  recurs.
- **DRY at three levels**: within the repo, against installed packages, against
  language built-ins. A reimplemented utility is `[minor]`, `[major]` if it
  drifts from behavior the library already gets right.
- **File size**: a diff pushing a file past roughly 1000 lines, or ad-hoc
  branches inserted into unrelated flows, is `[minor]`; it rises to `[major]`
  when the file was already over the limit and grew materially.
- **Convergent beats single-source.** Two independent lanes surfacing the same
  finding unprompted is high confidence; keep its severity. A `[major]` only
  one lane raised is accepted past `[minor]` on convergence, a reproduced
  failure, or a confirming verifier on the other model family
  (`rules/gates.md`, Independent Judgment); until then it is worth
  investigating, not worth blocking on.
- **A TRIVIAL diff on a CORE path** is reviewed as STANDARD with no review
  exception.
- **History audit before "wrong semantics".** Check whether an apparent
  regression is a deliberate reversal the history already justifies.
- **Pre-verdict claim check.** Before reporting no findings, name one claim the
  diff alone does not prove, check it in the repository, and state the check
  and its result. Typical claims: a title or commit type that hides a breaking
  change; a removed flag, command, endpoint, or UI affordance that docs or
  callers still reference; a pinned dependency, action SHA, or image digest
  that the repository uses inconsistently with what the change claims; a
  deleted symbol something still imports. When the diff is self-contained, say
  so.
- **Invalid findings**: formatting nits the formatter owns, personal style,
  demanding a specific implementation, and scope creep.
