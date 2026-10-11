# Check Existing Fix

Use when `fix-bug` or the cherry-pick skill needs to know whether a reported
bug is already fixed on the main branch, pending in an open PR, or still
unfixed. Git searches follow the scope rule in `debug/SKILL.md` (Notes).

## When to Skip

Skip this check when the primary change is not an isolated defect correction:
- Dependency upgrades or version bumps (even if tagged `fix`)
- Mixed PRs where the dominant change is a dependency or structural upgrade
- Refactors that happen to fix a side-effect

**Do not skip** when a dependency upgrade *exposes* a pre-existing bug. In that case the bug itself is the subject — the upgrade is context, not the fix. Classify as UNFIXED and continue.

When skipping, emit the output block with `Status: SKIPPED` and a one-line reason. The calling workflow still needs the block to branch on.

## Checks

Run these in parallel and merge the evidence:

1. **Upstream scan**: recent main-branch commits to the affected files, commits
   whose message names the bug, and merged PRs that match it.
2. **Open PR scan**: an open PR that appears to contain the fix.
3. **Release-target scan**, when the repository maintains several lines: the
   same search on the target branch.

## Output

Always return this block; the calling workflow branches on it.

```markdown
## Existing Fix Status

Status: FIXED_UPSTREAM / FIX_PENDING_PR / UNFIXED / SKIPPED

Upstream Evidence:
- <commit / PR, and the file:line or hunk that fixes the bug / not found>

Open PR Evidence:
- <PR and the hunk that would fix it / none>

Recommended Action:
- <route to cherry-pick / monitor PR / continue bug-fix workflow>
```

`FIX_PENDING_PR` is not the same as fixed. Use it to stop and surface the active PR context instead of coding blindly.
