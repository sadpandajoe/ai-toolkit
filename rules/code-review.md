# Code Review

## The Review Model

- **One independent review by default.** A fresh reviewer on the other
  provider (Codex Sol when Claude orchestrates, Claude Opus when Codex does)
  reviews the whole recorded diff once. It never sees the implementer's
  transcript.
- **Validate before fixing.** The reviewer is a critic, not an authority. The
  orchestrator checks each finding against the current repo and diff, records
  accepted versus rejected with a one-line reason for each rejection, and only
  then changes code.
- **Delta review, not a second full review.** After substantive remediation,
  one delta-only pass grades the fixes against the accepted findings. Mechanical
  fixes (renames, one-line reverts, formatting) need no second pass.
- **Deep lenses on flagged risk only.** The classifier's risk flags (security
  sensitivity, architecture change, refactor shape, explicit ask) add at most
  two `deep-review` lenses: adversarial, deep quality, or architecture.
- **Bounded rounds.** A review round is a reasoning unit under `rules/gates.md`:
  the same finding class surviving two rounds is `ESCALATE`, not round three.
- **Reviewer yield is measured.** Accepted findings per pass decides whether a
  lane keeps running; the observation queue records low-yield lanes.

## Core Principles

- **DRY at three levels**: within the repo, against installed packages, against
  language built-ins. A reimplemented utility is `[minor]`, `[major]` if it
  drifts from behavior the library already gets right.
- **Consistency and modeling**: follow neighboring patterns; logic lives where a
  future reader would look; signatures match neighbors.
- **File-size and spaghetti smells**: a diff pushing a file past roughly 1000
  lines, or ad-hoc branches inserted into unrelated flows, is a `[minor]`
  design prompt, `[major]` when it makes an existing flow materially harder to
  reason about.
- **Tests must be able to fail**: always-green tests are noise; data matches
  types.

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

## Finding Calibration

- **Scope is upstream of correctness.** Confirm the `file:line` is in the diff
  before grading. Unchanged code goes to Remaining, not findings.
- **The diff is the recorded base to HEAD in every round.** Never re-derive
  scope from the last fix delta; a defect the review itself introduced in round
  one must still be reportable in round two.
- **Symmetry findings cap at `[minor]`** unless the change plausibly covers or
  worsened the sibling path.
- **History audit before "wrong semantics".** Check whether an apparent
  regression is a deliberate reversal the history already justifies.
- **Do not steer the reviewer.** The prompt supplies diff facts, risk flags, and
  posture; never a finding shape.

## Invalid Findings

Formatting nits the formatter owns, personal style, demanding a specific
implementation, and scope creep.
