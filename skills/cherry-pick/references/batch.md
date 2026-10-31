# Batch Cherry-Pick

## Pre-flight

Run over the full list before any deep investigation and record the rows in
`CHERRY_PICK.md`:

```bash
<skill-dir>/scripts/batch-preflight.sh <target-branch> <pr-number | #pr | sha>...
```

One TSV row per request: `status`, `request`, `pr`, `sha`, `parents`,
`evidence`, `title`. PR rows need `gh`; SHA rows need only git. Don't spend
model work re-discovering what the table already says.

**The one "already applied" rule:** a request is on the target when the
target's first-parent history carries its PR number (not since reverted) or a
target commit carries its `cherry picked from commit <sha>` marker. A matching
title is advisory (`title-match (advisory)`) and never skips a row on its own.

- `ALREADY_APPLIED`: skip, unless you record a decision to pick it again.
- `NOT_MERGED`: record `Skipped/NOT_MERGED` and report it; never pick an
  unmerged head.
- `NEEDS_INVESTIGATION`: run the single-cherry flow.
- `PREFLIGHT_BLOCKED`: missing PR, unknown SHA, unfetched merge commit, or a
  `gh`/git failure.

`parents` of 2 or more is a merge commit ([apply.md](apply.md)).

## Ordering

```bash
<skill-dir>/scripts/batch-deps.sh --source <source-branch> --target <target-branch> <sha>...
```

It lists each SHA's files (a merge against its first parent), the pairs that
share files, the order on the source branch's first-parent line, and the fully
independent SHAs. Sort shared-file pairs topologically in first-parent order.

First-parent order is wrong when a later commit reverts, removes or refactors
what an earlier one touched: if A modifies file F and B later removes it,
applying B first lets A apply against the post-removal state. Merge order never
shows this; only the file overlap does, so inspect every such pair. Circular or
ambiguous chains go to the user.

## Execution

- Each cherry starts from clean context; independent rows may be investigated
  in parallel, but applying to the target stays sequential.
- Work done in an isolated worktree is replayed onto the live target in order,
  and the scope audit and validation re-run there before the row counts as
  applied or is pushed.
- Prefer small waves (down to one row) when rows share files, touch dependency
  manifests, migrations, generated files or API shapes, or form a chain. Wave
  size never weakens per-cherry validation or the per-cherry push.
- A failure or an unpushed row stops its dependents; independent rows continue.
- `--plan-only`: pre-flight, ordering and the per-cherry decision, then the
  table; nothing applied.
