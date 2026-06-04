# Final Report Format

Use this format at the end of every cherry-pick (single or batch). Lead with the ticket outcome — what the user cares about — then the execution table, then actionable residuals.

## Rules

- The compact 6-column table replaces the full 13-column execution table only in the final report. See [execution-table.md](execution-table.md) for the full table.
- Add **Detailed Notes** for any row that is not `Applied` with `None` adaptation, plus any `Applied` row with notable adaptation.
- Keep the dependency graph from the batch-sequence phase if inter-change dependencies were detected.
- For every `Blocked` or `Rejected` row, include the unblock-discovery result (step 7c) — either the candidate PR list or "no unblock path: <reason>". A bare "skipped because X" is not enough; the user needs to know what would make this cherry-pickable.
- "What to do next" is actionable only — no recap of what just happened.
- Lead with the ticket outcome. The user cares about "is the fix on the branch" more than about the process.
- **Scope Audit field is mandatory** for any row not in `Rejected` or `Skipped` — its absence means the leak-detection subagent did not run, which blocks `Applied`/`Partial`/`Blocked` status.

## Template

```markdown
## Cherry-Pick Summary

[1–2 lines answering the user's original question — e.g., "The StructuredContentStripperMiddleware (the encoding fix) is now active on this branch." or "The fix from #38837 is applied; CI re-run needed to confirm."]

[X of N applied, Y rejected, Z partial] -> <target branch>

### Results
| SHA | PR | Status | Scope Audit | Validation | Notes |
|-----|----|--------|-------------|------------|-------|
| `<sha>` | #123 | Applied | CLEAN | Tested | Clean apply |
| `<sha>` | #124 | Partial | CLEAN (1 hunk reverted) | Checked | 5 of 7 sub-fixes applied; encoding fix dropped — see below |
| `<sha>` | #125 | Rejected | — | — | Feature change, no --force |

### Detailed Notes
#### `<sha>` — <summary>
- **Why non-trivial**: [conflict, rejection reason, or intervention point]
- **Gate decision**: [PROCEED / REJECT / FORCE-PROCEED + criteria]
- **Adaptation details**: [What was modified and why]
- **What was dropped**: [specific functions, files, or sub-fixes omitted]
- **Residual risk**: [What remains uncertain]
- **Unblock path** (Blocked/Rejected rows only): "Could cherry if we first apply: #X, #Y, #Z" — or "no unblock path: <one-line reason>"

### What to do next
- [Actionable residual items — e.g., "encoding bug likely affects target via different code path — needs separate fix"]
- [Validation gaps — e.g., "run pytest tests/unit_tests/mcp_service/ before merging"]
- [Pending PRs to monitor — e.g., "#38676 still open — pick when merged"]
- [Unblock candidates from step 7c — e.g., "PR #39501 introduced StructuredContentStripper; #39636 wired it into middleware. Pick both first, then re-run /cherry-pick #39798."]
```
