# CHERRY_PICK.md and the Final Summary

## Row vocabulary

`CHERRY_PICK.md` is local working notes: target and source branch, the
pre-flight rows, waves, and one row per cherry. No diffs, raw logs or worker
transcripts; refs, one-line outcomes and short decisive excerpts only.

Row columns: Order, PR, Source SHA, Result, Target SHA, Scope Audit,
Validation, Push, Adaptation, Owner-notified, Notes.

- **Result:** `Planned`; `Applied` (landed, adapted or not); `Partial`
  (significant parts dropped, always with a note); `Blocked` (missing
  prerequisite, unresolvable conflict); `Rejected` (reject category, no
  `--force`); `Skipped` (already applied, not affected, not merged, or skipped
  by the user).
- **Scope Audit:** `CLEAN`, `LEAKED-REVERTED` or `ESCALATED`; required on
  `Applied` and `Partial`.
- **Validation:** the labels in [validate.md](validate.md).
- **Push:** `pushed <sha>`, `pending-authorization` (`--no-push`) or
  `deferred` (with a one-line reason).
- **Adaptation:** `None` (mechanical); `Minor` (import paths, renames, trivial
  API differences); `Medium` (logic rewritten for target APIs, or a functional
  subset of a mixed commit); `High` (functions, files or bug fixes dropped for
  missing architecture; the user must hear about it). Dropping significant
  chunks is `High`, never `Minor`.

## Final summary

Lead with the answer to the user's question (is the fix on the branch?), then
the table, then actionable next steps only, no recap.

```markdown
## Cherry-Pick Summary

<1–2 lines, e.g. "The encoding fix is now on 6.1-release; CI re-run needed to confirm.">

<X of N applied, Y rejected, Z partial> -> <target branch>

| SHA | PR | Status | Scope Audit | Validation | Notes |
|-----|----|--------|-------------|------------|-------|
| `<sha>` | #<pr> | Applied | CLEAN | Tested | Clean apply |
| `<sha>` | #<pr> | Partial | LEAKED-REVERTED | Checked | 5 of 7 sub-fixes; encoding fix dropped, see below |

### Detailed Notes
#### `<sha>` — <summary>
- Decision and any `--force` override; what was adapted, what was dropped; residual risk
- Unblock path (Blocked/Rejected): "Could cherry if we first apply #X, #Y — <difficulty>", or "no unblock path: <reason>"

### What to do next
- <e.g. "the encoding bug likely affects the target via another path; needs a separate fix">
- <validation gaps, pending PRs to pick once merged, unblock candidates>
```

Detailed notes are required for any row that is not `Applied` with `None`
adaptation; keep the dependency order when rows depended on each other.
