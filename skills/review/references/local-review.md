# Local Review Orchestration

Use for `review-code` on local uncommitted, staged, committed, or path-filtered
changes. The parent orchestrates; all review judgment comes from fresh lanes.

## Gather Changed Files

Default scope is branch-wide: `<base>..HEAD` plus the working tree and index.
`--committed` and `--uncommitted` narrow it; path arguments filter it. Read the
full contents of changed files, not only hunks.

<!-- aitk-model-route-exempt:pre-dispatch-condition -->
Before dispatching any reviewer, print one line so the user can intervene:
`Scope: <N> committed + <M> uncommitted files (<base>..HEAD = <sha>..HEAD)`.
Stop if the scope is empty.

**Record the base.** Resolve `<base>` once on round one and write it into the
Review Record. Every later round, including the delta pass, measures scope from
that recorded base, never from the last fix.

**Two bases.** The caller names which base this review measures. The **branch
base** (`<merge-base>..HEAD` plus the working tree) is the default for
standalone runs and the only base for an integrated review. A **phase base**
(the `tree` SHA the previous phase recorded with `bin/aitk project-state phase
--status done --sha <sha>`, shown by `project-state show` and as `Tree:` in its
`## Phase Complete`) is what per-unit reviews inside MULTI_PHASE or BATCHED
work pass, so a phase-three review reads phase three and
never re-reads phases one and two. The base is data in the snapshot, never a
remembered commit. The Review Record carries both: `Base` is the span this
review measured, `Branch base` is the merge-base the integrated review will
use.

**The reviewer sees the whole span.** Path arguments and `--uncommitted` narrow
what the parent grades and fixes, never what the independent lane receives:
the reviewer always gets the full recorded base to HEAD (branch or phase). When
the reviewer's span is wider than the user's filter, the Review Record says so
in `Scope note`.

## Classify

Run [classify-diff.md](classify-diff.md) and `qa/references/assess-impact.md`.
Record the complexity, impact, and risk flags in the Review Record. TRIVIAL
zero-logic or micro-fix diffs may take the review exception in `rules/gates.md`;
everything else gets the independent review below, even at TRIVIAL. A TRIVIAL
diff with CORE impact is reviewed as STANDARD: the exception is unavailable and
missing-test findings shift up one level (`rules/code-review.md`).

**Batched work reviews the transformation, not the waves.** For BATCHED work
the first wave gets the full independent review; later waves that apply the
same transformation run the verification loop only and record `Review: wave N
verification-only (transformation reviewed on wave 1)`. A wave that deviates
(hand edits, a new file kind, a changed transformation) gets its own lane, and
the integrated review checks the aggregate once at the end.

## Preflight

Run the repo's build, lint, typecheck, and the tests covering changed files
when quick enough. If preflight fails, fix it or record the blocker before any
review lane runs; the reviewer receives the preflight result.

## Independent Review

<!-- aitk-model-route:review.independent -->
Launch one fresh reviewer worker on `review`, on the other provider when
reachable; use `deep-review` only when the classifier's deep-tier escalation
fired. The prompt carries the diff and full changed files, the recorded base,
the preflight result, the classifier's flags and impact, and acceptance
criteria from `PROJECT.md` when relevant. It never carries the implementer's
transcript or any earlier findings. The worker receives its contract inline from
the route runner. If no cross-provider lane is reachable and the diff is neither
security-sensitive nor deep-tier, run the toolkit's same-provider reviewer
agent instead and record `Independent review: same-provider` in the Review
Record; never skip the lane and never review
inline. A security-sensitive or deep-tier diff with no cross-provider lane is
`## Gate: review` `BLOCKED (degraded)` until the other provider is reachable or
the user passes `--allow-degraded`, recorded as `USER_DECISION`
(`rules/gates.md`, Independent Judgment).

## Second Family (COMPLEX, CORE impact, or a clean verdict on a sizeable diff)

<!-- aitk-model-route:review.second-family -->
Launch one more fresh reviewer worker on `review` (`deep-review` under a
deep-tier escalation) on the provider the independent lane did not use, with
the same prompt and nothing from the first lane, when the classifier reports
COMPLEX or CORE impact, or when the **clean-verdict guard** fires: the
independent lane returned zero findings on a STANDARD diff above 200 changed
lines or 5 files (generated files and lockfiles excluded). A clean verdict on
that much surface is more often a miss than perfection, so the second family
runs after the fact rather than concurrently, and the Review Record notes
`Second family: clean-verdict guard`. The two lanes merge under the
convergence rule in `rules/code-review.md`: raised by both → keep the severity;
raised by one → capped at `[minor]` until the parent's validation names the
concrete failure. No verifier lane runs when this lane ran; the second family
already answered. On a Claude parent this lane is the Opus reviewer agent and
spends Claude quota, while the Codex lane spends none, which is why STANDARD
diffs stay at one lane. Skip it and disclose when the second provider is
unreachable and the diff is not security-sensitive; a security-sensitive diff
is `BLOCKED (degraded)` as above.

## Deep Lenses (conditional)

<!-- aitk-model-route:review.deep-lenses -->
When the classifier flagged risk, launch at most two additional fresh worker
lanes on `deep-review`, one per flagged lens, concurrently with the independent
review: [adversarial.md](adversarial.md) for security-sensitive diffs or a
red-team ask, [deep-quality.md](deep-quality.md) for refactor-shaped or
deep-quality asks, and
[../../plan-review/references/architecture.md](../../plan-review/references/architecture.md)
for architecture changes. Each lane is resolved with `--lens <repo-relative
lens path>` so one worker receives exactly one lens. No flags means no deep
lanes. A code-judo ask runs at its own boundary
([code-judo.md](code-judo.md)) and returns proposals, not findings.

## Validate, Then Fix

Collect findings from every lane and dedupe by file, line, and class. For each
`[major]` and `[minor]`, check the claim against the current repo and diff
before changing anything: accepted, or rejected with a one-line evidence-based
reason.

A `[major]` that only one lane raised is never accepted on the parent's reading
alone, and never **rejected** on it either: a `[major]` the parent intends to
reject goes to the same verifier, and the rejection stands only on `REFUTED`
or `UNVERIFIABLE`; `CONFIRMED` overrides the parent and the finding is
accepted at the verifier's severity. A finding two lanes raised independently
needs no verifier, and when the second-family lane ran, its silence is the
second family's answer (cap at `[minor]` unless validation names the
failure). The verifier below is for reviews where a single independent lane
ran, in both directions.
<!-- aitk-model-route:review.verify-major -->
Launch one fresh verifier worker on `review` (`deep-review` when the review ran
deep) on the model family that did not raise the finding, with only the finding,
the diff, and the full changed files; it returns `Verdict: CONFIRMED | REFUTED |
UNVERIFIABLE` with a concrete failure scenario. `CONFIRMED` keeps the severity;
`REFUTED` records the finding as rejected with the verifier's evidence;
`UNVERIFIABLE` caps it at `[minor]` until the parent settles the fact the
verifier named. On a single-provider machine (Codex unreachable) the
independent lane ran on Opus and the second family was skipped, so a
`review`-route verifier would be Opus again: run the verifier on `deep-review`
(Fable) instead, or leave the finding capped at `[minor]` and record
`Verifier: unavailable — single family` in the Review Record. A verifier on the
family that raised the finding is not a verifier.

Write the Review Record to `PROJECT.md` before fixing. Then apply
accepted fixes (parent inline, or the implementer worker for a large queue),
add the locking tests the findings named, and run the verification loop
(`skills/verification-loop/SKILL.md`) on the fixed files.

**Reviewer-reported flags.** When a lane's summary carries `Missing flag:
<security-sensitive | architecture | refactor-shaped> — <file:line evidence>`,
the parent re-runs [classify-diff.md](classify-diff.md) with that evidence. A
flag that fires now adds its lens through the Deep Lenses boundary above (the
usual cap of two still holds) and the Review Record notes
`Reclassified: <flag> on reviewer evidence`. A flag the classifier still does
not confirm is recorded as rejected with the reason; the reviewer's word alone
does not launch a lens.

Disputed findings and genuine trade-offs surface as `USER_DECISION`; everything
else is decided here.

## Delta Review

Before the delta pass, re-run [classify-diff.md](classify-diff.md) against the
recorded span. A fix can add a security-sensitive path, an architecture
change, or refactor shape the original diff did not have; a flag that fires now
adds its deep lens to the delta round through the Deep Lenses boundary above,
and the Review Record notes the reclassification.

<!-- aitk-model-route:review.delta -->
Launch one fresh delta reviewer worker on `review` (`deep-review` if the original
ran deep) after substantive remediation: new branches, helpers, fixtures, guard
clauses, or any `[major]` fix. The prompt marks it a delta review and
carries the accepted findings, the fix diff, and the recorded base; the worker
grades fixed / not fixed / fixed-but-introduced and reviews new code paths only.
Skip the delta pass when every fix was a deletion, one-line revert, formatting,
or comment. A finding class surviving the delta pass is `ESCALATE` under
`rules/gates.md`, not a third round.

## Gate and Record

Emit the gate block from `rules/gates.md` as `## Gate: review` with
`Independent review: <provider/family | same-provider>`, `Deep lenses: <names
or none>`, `Findings: <accepted>/<raised> accepted`, and `Delta: <clean |
reopened N | not required>` on the Evidence line. Record it with
`bin/aitk project-state gate --gate review --status <...>`.

Review Record in `PROJECT.md` (compact, actionable only):

```markdown
## Current Code Review
**Base:** <sha — resolved on round 1, reused by every round; phase base for a per-unit review>
**Branch base:** <merge-base sha — the integrated review's span; same as Base for standalone runs>
**Scope:** <files or filter | integrated>
**Scope note:** <none | reviewer span wider than the filter: <what it covered>>
**Preflight:** <pass/fail/skipped — command or reason>
**Independent review:** <provider/family | same-provider>
**Second family:** <provider/family — COMPLEX | CORE | clean-verdict guard, or not run — <reason>>
**Reclassified:** <none | <flag> on reviewer evidence <file:line>>
**Lane yields:** <lane: accepted/raised, … | demoted: <lane> (<yield> over <n> runs)>
**Deep lenses:** <names, or none> — <flags that triggered them>
**Verified majors:** <R-ids → CONFIRMED / REFUTED / UNVERIFIABLE, or none>
**Gate:** <PASS | RETRY | ESCALATE | USER_DECISION | BLOCKED>

### Findings
| ID | Severity | File | Finding | Locking assertion | Verdict | Status |
|----|----------|------|---------|-------------------|---------|--------|
| R1 | major | path:line | concise issue | assertion, or n/a | accepted / rejected: <reason> | open / fixed / user-decision |

### Restructuring Proposals
<!-- only when a code-judo pass ran; never auto-applied -->

### Fix Queue
- [ ] R1 — <next action>

### Resume Notes
- Next: <fix R1 / delta review / emit gate / continue caller>
```

`Findings: none` with a `PASS` gate is a complete record. Reviewer yield
(accepted/raised per lane, plus converged for the second family) feeds the
metrics event's `review.lanes` and the observation queue; the thresholds and
their consequences are in `rules/code-review.md`, Yield Thresholds, and the
parent applies them before dispatching an optional lane, recording
`Lane demoted: <lane> (<accepted>/<raised> over <n> runs)` when one applies.

## Summary (standalone runs only)

```markdown
## Review-Code Complete
Gate: <status> | Independent review: <lane> | Deep lenses: <names or none>
Findings: <accepted>/<raised> accepted, <fixed> fixed
### Fixed
### Rejected (with reason)
### Remaining
```
