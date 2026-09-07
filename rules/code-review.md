# Code Review

## The Review Model

- **One independent review by default.** A fresh reviewer on the other
  provider (Codex Sol when Claude orchestrates, Claude Opus when Codex does)
  reviews the whole recorded diff once. It never sees the implementer's
  transcript. COMPLEX and CORE-impact diffs add one more lane on the other
  family, concurrently and cold; the two merge by convergence. Breadth is
  bounded at two families; depth is never added by another round.
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

## Review Shape by Tier

Depth follows the decision surface, never the diff size. The cap is the
tier's, and a simpler tier never inherits a deeper one's rounds.

| Tier or shape | Lanes | Delta pass | Notes |
|---|---|---|---|
| TRIVIAL | exception, or one lane when any logic changed | none: fixes are re-verified, not re-reviewed | a fix that adds logic reclassifies to STANDARD |
| STANDARD | one lane | one, only after a substantive fix | the default for real, contained work |
| COMPLEX or CORE impact | one lane plus the second family, deep lenses on flags | one | convergence merges the lanes |
| BATCHED | one lane on the first wave; later identical waves are verification-only | one, on the reviewed wave | a wave that deviates from the transformation gets its own lane; the integrated review checks the aggregate |
| MULTI_PHASE | per phase by that phase's tier, on the phase base | per phase | one integrated review over the branch base before completion |

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
- **Convergent beats single-source.** Two independent lanes surfacing the same
  finding unprompted is high confidence; keep its severity. A `[major]` only
  one lane raised is verified by a fresh lane on the other model family before
  it blocks (`rules/gates.md`, Independent Judgment); until then it is worth
  investigating, not worth blocking on.
- **CORE impact shifts missing-test findings up one level**, and a TRIVIAL diff
  on a CORE path is reviewed as STANDARD with no review exception.
- **History audit before "wrong semantics".** Check whether an apparent
  regression is a deliberate reversal the history already justifies.
- **Do not steer the reviewer.** The prompt supplies diff facts, risk flags, and
  posture; never a finding shape.

## Invalid Findings

Formatting nits the formatter owns, personal style, demanding a specific
implementation, and scope creep.
