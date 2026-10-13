# Local Review Orchestration

Use for `review-code` on local uncommitted, staged, committed, or path-filtered
changes. Review judgment comes only from fresh lanes. `bin/aitk review plan`
decides which lanes run, `bin/aitk review merge` merges what they return, and
`bin/aitk project-state gate` records the gate; this file is the judgment those
commands leave to the parent.

## Scope and Base

Default scope is branch-wide: `<base>..HEAD` plus the working tree and index;
`--committed`, `--uncommitted` and path arguments narrow what the parent grades
and fixes. Before any lane runs, print `Scope: <N> committed + <M> uncommitted
files (<base>..HEAD = <sha>..HEAD)` and stop on an empty scope. Resolve the
base once, on round one, and record it; every later round, the delta pass
included, measures from that base. Per-unit reviews in MULTI_PHASE or BATCHED
work pass the phase base (the `tree` SHA `project-state phase --status done
--sha` recorded); the branch base is for standalone runs and the integrated
review. **The reviewer sees the whole span**: a filter never narrows what a
lane receives, and the Review Record's `Scope note` says when the span is
wider than the filter.

## Plan the Lanes

Run [classify-diff.md](classify-diff.md) and `qa/references/assess-impact.md`,
then the repo's quick preflight (build, lint, typecheck, tests on changed
files). Run `bin/aitk review plan --parent <your provider> --impact <impact>`
with the semantic flags and launch what it prints: lanes, providers, the
verifier family, the delta rule, yield demotions, or `BLOCKED (degraded)`. A
TRIVIAL zero-logic or micro-fix diff may take the review exception in
`rules/gates.md`. BATCHED work reviews the transformation: wave one gets the
full review, later identical waves record `Review: wave N verification-only`,
and a deviating wave gets its own lane.

<!-- aitk-model-route:review.independent -->
Launch the independent reviewer on `review` (`deep-review` on a deep-tier
escalation) on the provider the plan names, with the diff, the full changed
files, the recorded base, the preflight result, the flags and impact, never the
implementer's transcript or earlier findings.
<!-- aitk-model-route:review.second-family -->
When the plan lists the second family, launch it concurrently and cold through
`bin/aitk model-run review --provider <other provider> --boundary
review.second-family`.
<!-- aitk-model-route:review.deep-lenses -->
Launch each deep lens the plan lists on `deep-review` with `--lens <lens
path>`, one lens per worker. A code-judo ask runs at its own boundary
([code-judo.md](code-judo.md)) and returns proposals, not findings.

## Validate, Then Fix

Merge with `bin/aitk review merge --result <lane>=<envelope> …`; it dedupes,
counts convergence, applies the coverage rule and lists the single-source
majors. Check each `[major]` and `[minor]` against the current repo and record
it accepted, or rejected with a one-line evidence line. A finding that says the
slice, acceptance criterion or RCA is wrong is `RECLASSIFY`, whatever its
severity.

<!-- aitk-model-route:review.verify-major -->
A single-source `[major]` is neither accepted nor rejected on a reading. Accept
it once the failure reproduces or its locking assertion fails; otherwise launch
the verifier on the family the merge names, with only the finding, the diff and
the changed files. It works in both directions: `CONFIRMED` overrides a
rejection; `REFUTED` lets it stand; `UNVERIFIABLE` caps the finding at
`[minor]`. With no other family reachable, cap it and record `Verifier:
unavailable — single family`.

A lane's `Missing flag: <flag> — <file:line>` re-runs classify-diff with that
evidence; only a flag the classifier then confirms adds its lens (`Reclassified:
<flag> on reviewer evidence`). Disputes and genuine trade-offs become
`USER_DECISION`; decide everything else here. Write the Review Record, apply
the accepted fixes, add the locking tests the findings named, and verify the
fixed files with `skills/verification-loop/SKILL.md`.

## Delta Review

Remediation is substantive when it adds branches, helpers, fixtures or guard
clauses, or fixes a `[major]`; deletions, one-line reverts, formatting and
comments get no delta. Re-run classify-diff on the recorded span first: a flag
that fires now adds its lens to the delta round.
<!-- aitk-model-route:review.delta -->
Launch one delta reviewer on `review` (`deep-review` if the review ran deep)
with the accepted findings, the fix diff and the recorded base; it grades fixed,
not fixed, or fixed-but-introduced. A finding class that survives the delta is
`ESCALATE`, never a third round.

## Integrated Review

MULTI_PHASE and BATCHED work ends with one more review over the recorded branch
base after the last unit's checkpoint, checked against each phase's exit goal
and the global invariants, with its own `## Gate: review (integrated)` block and
a Review Record marked `Scope: integrated`. Fix a finding in the phase that owns
the code; the integrated delta runs once.

## Gate and Record

Record the gate with `bin/aitk project-state gate --gate review --status <...>
--result <envelope> … --format block`, one saved `model-run` envelope per lane,
and paste the block. A PASS without a reviewer envelope (or an exception on a
passing `verify --run`) does not count for `bin/aitk deliver`.

```markdown
## Current Code Review
**Base:** <sha, round 1> | **Branch base:** <merge-base> | **Scope:** <filter | integrated>
**Scope note:** <none | reviewer span wider than the filter>
**Lanes:** <independent provider/family | same-provider>; <second family | not run — reason>; <deep lenses or none>
**Verified majors:** <R-ids → CONFIRMED / REFUTED / UNVERIFIABLE, or none>
**Gate:** <PASS | RETRY | ESCALATE | USER_DECISION | BLOCKED>

| ID | Severity | File | Finding | Locking assertion | Verdict | Status |
|----|----------|------|---------|-------------------|---------|--------|

Next: <fix R1 / delta review / continue caller>
```

Standalone runs end with `## Review-Code Complete`: the gate, the lanes,
accepted/raised, and the fixed, rejected (with reason) and remaining findings.
