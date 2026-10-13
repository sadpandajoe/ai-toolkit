# Final Report Format

Use this format at the end of every cherry-pick, single or batch. Lead with the
ticket outcome (is the fix on the branch?), then the table, then actionable
residuals.

## Rules

- The compact table below replaces the full `CHERRY_PICK.md` execution table
  ([manifest](../templates/cherry-pick-manifest.md)) only in this report; keep
  the dependency graph when rows depended on each other.
- Add **Detailed Notes** for any row that is not `Applied` with `None`
  adaptation; every `Blocked` or `Rejected` row carries its unblock path or
  "no unblock path: <reason>", never a bare "skipped because X".
- **Scope Audit** is required on every `Applied` or `Partial` row; `Blocked`,
  `Rejected` and `Skipped` rows are exempt. "What to do next" is actionable
  only, no recap.

## Template

```markdown
## Cherry-Pick Summary

[1–2 lines answering the user's original question, e.g. "The encoding fix is now active on this branch." or "The fix from #<pr> is applied; CI re-run needed to confirm."]

[X of N applied, Y rejected, Z partial] -> <target branch>

### Results
| SHA | PR | Status | Scope Audit | Validation | Notes |
|-----|----|--------|-------------|------------|-------|
| `<sha>` | #<pr> | Applied | CLEAN | Tested | Clean apply |
| `<sha>` | #<pr> | Partial | LEAKED-REVERTED | Checked | 5 of 7 sub-fixes applied; encoding fix dropped, see below |
| `<sha>` | #<pr> | Rejected | — | — | Feature change, no --force |

### Detailed Notes
#### `<sha>` — <summary>
- **Why non-trivial**: [conflict, rejection reason, or intervention point]
- **Gate decision**: [PROCEED / REJECT / FORCE-PROCEED + criteria]
- **Adaptation details**: [What was modified and why]
- **What was dropped**: [specific functions, files, or sub-fixes omitted]
- **Residual risk**: [What remains uncertain]
- **Unblock path** (Blocked/Rejected rows only): "Could cherry if we first apply: #X, #Y, #Z — <difficulty>" — or "no unblock path: <one-line reason>"

### What to do next
- [Actionable residual items, e.g. "encoding bug likely affects target via a different code path; needs a separate fix"]
- [Validation gaps, e.g. "run <targeted test suite> before merging"]
- [Pending PRs to monitor, e.g. "#<pr> still open; pick when merged"]
- [Unblock candidates, e.g. "#X introduced the missing module and #Y wired it in. Pick both first, then re-run cherry-pick for #Z."]
```
