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

## Classify

Run [classify-diff.md](classify-diff.md) and `qa/references/assess-impact.md`.
Record the complexity, impact, and risk flags in the Review Record. TRIVIAL
zero-logic or micro-fix diffs may take the review exception in `rules/gates.md`;
everything else gets the independent review below, even at TRIVIAL. A TRIVIAL
diff with CORE impact is reviewed as STANDARD: the exception is unavailable and
missing-test findings shift up one level (`rules/code-review.md`).

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

## Second Family (COMPLEX or CORE impact)

<!-- aitk-model-route:review.second-family -->
Launch one more fresh reviewer worker on `review` (`deep-review` under a
deep-tier escalation) on the provider the independent lane did not use, with
the same prompt and nothing from the first lane, when the classifier reports
COMPLEX or CORE impact. The two lanes run concurrently and merge under the
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
alone; a finding two lanes raised independently needs no verifier, and when the
second-family lane ran, its silence is the second family's answer (cap at
`[minor]` unless validation names the failure). The verifier below is for
reviews where a single independent lane ran.
<!-- aitk-model-route:review.verify-major -->
Launch one fresh verifier worker on `review` (`deep-review` when the review ran
deep) on the model family that did not raise the finding, with only the finding,
the diff, and the full changed files; it returns `Verdict: CONFIRMED | REFUTED |
UNVERIFIABLE` with a concrete failure scenario. `CONFIRMED` keeps the severity;
`REFUTED` records the finding as rejected with the verifier's evidence;
`UNVERIFIABLE` caps it at `[minor]` until the parent settles the fact the
verifier named.

Write the Review Record to `PROJECT.md` before fixing. Then apply
accepted fixes (parent inline, or the implementer worker for a large queue),
add the locking tests the findings named, and run the verification loop
(`skills/verification-loop/SKILL.md`) on the fixed files.

Disputed findings and genuine trade-offs surface as `USER_DECISION`; everything
else is decided here.

## Delta Review

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
**Base:** <sha — resolved on round 1, reused by every round>
**Scope:** <files or filter>
**Preflight:** <pass/fail/skipped — command or reason>
**Independent review:** <provider/family | same-provider>
**Second family:** <provider/family, or not run — <reason>>
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
(accepted/raised) feeds the metrics event and the observation queue.

## Summary (standalone runs only)

```markdown
## Review-Code Complete
Gate: <status> | Independent review: <lane> | Deep lenses: <names or none>
Findings: <accepted>/<raised> accepted, <fixed> fixed
### Fixed
### Rejected (with reason)
### Remaining
```
