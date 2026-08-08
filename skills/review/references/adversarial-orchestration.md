---
tier: Heavy
---

# Adversarial Review Orchestration

<!-- aitk-model-route-exempt:describes-reviewers-not-dispatch -->
Use for `review-code-adversarial`. This coordinates red-team reviewers; [adversarial.md](adversarial.md) is the reviewer lens prompt.

## Discover Changed Files

- Default: combine unstaged and staged diffs.
- `--committed`: compare from merge-base to `HEAD`.
- Path args: filter to matching files.

Resolve committed base with the remote-tracking default branch:

```bash
base_branch=$(git remote show origin | sed -n 's/.*HEAD branch: //p')
base_branch=${base_branch:-main}
git merge-base HEAD origin/$base_branch
```

Read full file contents and diff context.

## Launch Reviewers

This workflow runs the `security` ensemble from [ensemble.md](ensemble.md): a
three-vote panel spanning **both** providers, every adversarial lane on
`deep-review`. Resolve the exact roster first:

```bash
<toolkit-root>/bin/aitk review-ensemble security --provider <origin> --available <reachable> --json
```

<!-- aitk-model-route:review.adversarial-cross-provider-panel -->
Dispatch the resolved panel reviewers in parallel through `bin/aitk model-run --provider <provider>`, one per resolved lane: the origin-provider adversarial lane on `deep-review` using [adversarial.md](adversarial.md), the cross-provider cold adversarial lane on `deep-review` (scope and diff only, never the origin lane's findings), and the origin third-vote lane. Three lanes on one model is not this panel — it is a single-model review with extra cost.

The panel is `block`-on-degraded: if the cross provider is unreachable, report
the resolver's disclosure and stop, or continue only on an explicit user
override with the disclosure retained. Never substitute another model for the
missing provider, and never describe a single-provider run as a multi-model
panel.

## Merge Findings

Deduplicate findings, merging each finding's `provider/family` provenance rather
than collapsing it:

- Found by lanes on **different providers**: convergent, high confidence — keep severity.
- Found by two lanes on the same model family: agreement, not independence — treat as one lane's finding.
- Unique to one reviewer: include at normal confidence; verify with a lane from a different provider before promoting past `[minor]`.

Draw those verifying lanes from `select_verifiers()` on the resolved `security`
roster — never the origin lane, never the same lane twice. It returns up to the
tier's two, and fewer when the roster cannot supply them; record the vote count
actually achieved (`verified 1/2`) rather than implying a full panel. That count
is the verifier tally, not the three-lane panel roster above.

Apply the finding calibration in `rules/code-review.md` before sorting: drop any finding whose `file:line` is not in the diff (scope is upstream of correctness — settle this before adjudicating whether the two reviewers disagree on a bug's reality), and cap unchanged-sibling symmetry findings at `[minor]`.

Sort by risk:

1. Vulnerability.
2. Race condition.
3. Data integrity issue.
4. Missing validation.
5. Edge case.

## Fix + Verify

Every concrete finding must be addressed, rejected with evidence, or surfaced as a user decision.

After each fix:

- Run targeted checks.
- Re-review the fixed files through the adversarial lens.
- Iterate until clean or blocked.

## Review Gate

```markdown
## Review Gate
Rounds: [N]
Pre-flight: [pass/fail/skipped]
Status: [clean/blocked/user decision]
Adversarial Rating: [Hardened/Adequate/Vulnerable/Critical]
Reviewers: [resolved panel lanes as provider/family | primary only]
Model coverage: [provider-diverse/family-diverse/single-family] [+ disclosure when below floor]
```

Never claim dual-reviewer coverage when only one reviewer ran, and never claim
multi-model coverage when every lane ran on one model family.

## Summary

```markdown
## Review-Code-Adversarial Complete
Rating: [Hardened/Adequate/Vulnerable/Critical] | Rounds: [N] | Status: [clean/blocked]
Reviewers: [resolved panel lanes as provider/family | primary only]
Model coverage: [provider-diverse/family-diverse/single-family] [+ disclosure when below floor]

### Findings
- [N] high confidence, [N] primary only, [N] second-opinion only

### Fixed
- [...]

### Accepted Risks
- [...]
```
