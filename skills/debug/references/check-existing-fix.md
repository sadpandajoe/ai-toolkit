---
tier: Standard
---

# Check Existing Fix

Use this helper when a workflow needs to know whether a reported bug is already fixed in `master`, pending in an open PR, or still unfixed.

This is a shared helper for `developer`, `release-engineer`, and workflows such as `fix-bug` and `$cherry-pick`.

## When to Skip

Skip this check when the primary change is not an isolated defect correction:
- Dependency upgrades or version bumps (even if tagged `fix`)
- Mixed PRs where the dominant change is a dependency or structural upgrade
- Refactors that happen to fix a side-effect

**Do not skip** when a dependency upgrade *exposes* a pre-existing bug. In that case the bug itself is the subject — the upgrade is context, not the fix. Classify as UNFIXED and continue.

When skipping, emit the output block with `Status: SKIPPED` and a one-line reason. The calling workflow still needs the block to branch on.

## Goal

Run the relevant checks in parallel, merge the evidence, and return one normalized outcome that the calling workflow can act on.

## Git Scope

All checks below are scoped to master, the current branch, and merged PRs. Do not use `git log --all` — unmerged branches may contain experimental or unvetted implementations that were never shipped.

## Parallel Checks

Run the relevant checks in parallel:

1. `upstream scan`
   - Is the bug already fixed in `master`?
   - Check: `git log master -- <affected-files>` for recent changes to the area
   - Check: `git log master --grep="<bug keyword>"` for fix-related commits
   - Check: `gh pr list -R <repo> --state merged --search "<bug keyword>"` for merged PRs

2. `open PR scan`
   - Is there an open PR that appears to contain the fix but is not merged yet?
   - Check: `gh pr list -R <repo> --state open --search "<bug keyword or affected area>"`

3. `release-target scan` when needed
   - If the repository supports multiple maintained lines, check the relevant target line as well.
   - Check: `git log <target-branch> -- <affected-files>`

## Output

Always return the normalized summary block below. The calling workflow branches on this output — gathering the evidence without producing this block is not sufficient.

```markdown
## Existing Fix Status

Status: FIXED_UPSTREAM / FIX_PENDING_PR / UNFIXED / SKIPPED
Confidence: X/10

Upstream Evidence:
- <commit / PR / not found>

Open PR Evidence:
- <PR / none>

Recommended Action:
- <route to cherry-pick / monitor PR / continue bug-fix workflow>
```

`FIX_PENDING_PR` is not the same as fixed. Use it to stop and surface the active PR context instead of coding blindly.
