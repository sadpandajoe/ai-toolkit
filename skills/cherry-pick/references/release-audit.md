---
tier: Standard
---

# Release Audit — What Hasn't Reached the Release Branch

Answers "what is on `<source>` that isn't on `<release-branch>`?" — backport-candidate discovery before any cherry list exists. This is discovery, not application: every candidate it surfaces still runs the full investigate/gate flow.

## The Failure Mode This Kills

Comparing raw commit logs between branches produces noise: a branch diff of "1,400 commits" where almost all are inner commits of already-merged feature branches, plus false "already applied" matches from PR-title greps. First-pass analyses built on that data start from a wrong universe and burn correction rounds.

## Methodology (three rules)

1. **First-parent only, both sides, since the merge-base.** Each first-parent commit on the source branch is one PR (merge commit or squash). Inner commits of merged branches are never units of backporting — exclude them from the universe entirely.
2. **"Already on target" requires exact evidence.** Either the same PR number in the *target's own* first-parent history, or a `cherry picked from commit <sha>` (`-x`) marker pointing at the exact source SHA. A PR-title or subject grep alone is advisory — same rule as the batch pre-flight in SKILL.md.
3. **Verify candidates with `gh pr view` before queuing.** For each MISSING row: `gh pr view <n> --json state,mergedAt,baseRefName,title,labels`. This confirms the PR is actually merged, targeted the expected base, and the extracted `#N` wasn't a revert/issue cross-reference in the subject.

## Run It

```bash
git fetch origin master 6.1-release   # always audit remote refs, not stale local ones
${CLAUDE_SKILL_DIR}/scripts/release-audit.sh origin/6.1-release origin/master
```

Output is TSV (`status`, short sha, PR number, subject), oldest first. Statuses: `MISSING` (candidate), `PRESENT-BY-PR`, `PRESENT-BY-CHERRY-MARK`.

## Interpreting Results

- **MISSING rows are candidates, not a cherry list.** Filter by what the release actually needs (fix vs feature, labels, ticket scope), then verify per rule 3, then hand the survivors to the normal flow (`--plan-only` first for big sets).
- **Check for reverts before queuing.** A MISSING PR followed by a later `Revert "..."` row for the same change nets to zero — queue neither.
- **`pr: -` rows** are direct pushes or squashes that lost their `(#N)` suffix. They have no PR-number evidence on either side, so eyeball them manually; the script can only report them as MISSING.
- **PRESENT-BY-PR with divergent content is possible** (a prior backport was adapted). If a row matters, spot-check with `git show` — presence means "this PR was represented", not "the diffs are identical".

For batch runs, record the audit table (or its MISSING subset) in `CHERRY_PICK.md` under the pre-flight section so the candidate universe survives checkpoint/clear.
