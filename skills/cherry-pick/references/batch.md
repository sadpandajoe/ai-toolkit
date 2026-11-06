# Batch Cherry-Pick

## Pre-flight

Over the full list, before any deep investigation; record the rows in
`CHERRY_PICK.md`:

```bash
<skill-dir>/scripts/batch-preflight.sh <target-branch> <pr-number | #pr | sha>...
```

One TSV row per request: `status`, `request`, `pr`, `sha`, `parents`,
`evidence`, `title`. PR rows need `gh`; SHA rows need only git.

A request is already on the target when the target's first-parent history
carries its PR number (not since reverted) or a target commit carries its
`cherry picked from commit <sha>` marker. A title match is advisory and never
skips a row on its own.

- `ALREADY_APPLIED`: skip, unless you record a decision to pick it again.
- `NOT_MERGED`: record `Skipped/NOT_MERGED`; never pick an unmerged head.
- `NEEDS_INVESTIGATION`: the single-cherry flow.
- `PREFLIGHT_BLOCKED`: missing PR, unknown SHA, unfetched merge commit, or a
  `gh`/git failure.

## Ordering

```bash
<skill-dir>/scripts/batch-deps.sh --source <source-branch> --target <target-branch> <sha>...
```

It lists each SHA's files, the pairs that share files, the source's
first-parent order and the fully independent SHAs. Apply shared-file pairs in
first-parent order, except where a later commit reverts, removes or refactors
what an earlier one touched: if A modifies file F and B later removes it,
applying B first lets A apply against the post-removal state, and merge order
never shows this. Inspect every overlapping pair; circular or ambiguous chains
go to the user.

## Execution

Rows may be investigated in parallel, but applying to the target is
sequential. Work done in an isolated worktree counts only once it is replayed
onto the live target and its scope audit and validation re-run there. A failed
or unpushed row stops its dependents; independent rows continue.
`--plan-only` ends at the table with nothing applied.
