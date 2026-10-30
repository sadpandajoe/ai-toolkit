# Release Audit

"What is on `<source>` that isn't on `<release-branch>`?" This finds backport
candidates; every candidate still goes through the normal cherry flow.

Raw commit-log comparisons between branches are noise: "1,400 commits" that are
mostly inner commits of already-merged feature branches, plus false "already
applied" matches from title greps. Analyses built on that start from the wrong
universe. Three rules:

1. **First-parent only, both sides, since the merge-base.** Each first-parent
   commit on the source is one PR (merge or squash); inner commits are never
   backport units.
2. **"Already on target" needs exact evidence:** the same PR number in the
   target's own first-parent history, or a `cherry picked from commit <sha>`
   marker for the exact source SHA. A title match is advisory (the same rule as
   the batch pre-flight).
3. **Verify each candidate before queuing:** `gh pr view <n> --json
   state,mergedAt,baseRefName,title,labels` confirms it merged, targeted the
   expected base, and that the `#N` in the subject wasn't a revert or issue
   cross-reference.

Preset's private repositories are reachable only from the corporate VPN; a
fetch or `gh` call that times out there means no VPN, not an empty result.

```bash
git fetch origin master 6.1-release   # audit remote refs, never stale local ones
<skill-dir>/scripts/release-audit.sh origin/6.1-release origin/master
```

TSV, oldest first: `status`, short SHA, PR number, subject. Statuses:
`MISSING` (candidate), `PRESENT-BY-PR`, `PRESENT-BY-CHERRY-MARK`.

- `MISSING` rows are candidates: filter by what the release needs (fix vs
  feature, labels, ticket scope), verify per rule 3, then run the flow
  (`--plan-only` first for big sets).
- A `MISSING` PR followed later by a `Revert "..."` of it nets to zero; queue
  neither.
- `pr: -` rows are direct pushes or squashes that lost their `(#N)` suffix;
  there is no PR evidence either way, so check them by hand.
- `PRESENT-BY-PR` can still differ in content (an adapted earlier backport);
  spot-check with `git show` when the row matters.

On batch runs, keep the audit table (or its `MISSING` subset) in
`CHERRY_PICK.md` so it survives a new session.
