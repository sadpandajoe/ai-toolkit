---
tier: Heavy
---

# Adversarial Review Orchestration

Use for `/review-code-adversarial`. This coordinates red-team reviewers; [adversarial.md](adversarial.md) is the reviewer lens prompt.

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

Run in parallel when available:

- Primary adversarial reviewer using [adversarial.md](adversarial.md).
- Optional second-opinion adversarial reviewer when the runtime supports one.

If no second-opinion reviewer is available, continue with the primary reviewer and state that clearly.

## Merge Findings

Deduplicate findings:

- Found by both independent reviewers: high confidence — keep severity.
- Unique to one reviewer: include at normal confidence; verify before promoting past `[minor]`.

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
Reviewers: [primary + second opinion | primary only]
```

Never claim dual-reviewer coverage when only one reviewer ran.

## Summary

```markdown
## Review-Code-Adversarial Complete
Rating: [Hardened/Adequate/Vulnerable/Critical] | Rounds: [N] | Status: [clean/blocked]
Reviewers: [primary + second opinion | primary only]

### Findings
- [N] high confidence, [N] primary only, [N] second-opinion only

### Fixed
- [...]

### Accepted Risks
- [...]
```
