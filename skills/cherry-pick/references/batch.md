# Batch Cherry-Pick Flow

When multiple PRs/SHAs are provided, the main agent is a **thin
orchestrator**: it owns ordering, dependency tracking, user decisions,
checkpoints and final synthesis, and does not accumulate raw per-cherry
context. **Each cherry starts with clean context**, so cherry N never inherits
earlier diffs and decisions.

## Deterministic Batch Pre-Flight

Before deep investigation, run the pre-flight over the full list and write its
rows into `CHERRY_PICK.md`:

```bash
<skill-dir>/scripts/batch-preflight.sh <target-branch> <pr-number | #pr | sha>...
```

It prints one TSV row per request (`status`, `request`, `pr`, `sha`, `parents`,
`evidence`, `title`) from `gh pr view --json` and the target's history. PR rows
need `gh`; SHA rows need only git.

**The one "already applied" evidence rule:** a request is present on the target
when the target's first-parent history carries its PR number (not since
reverted) or a target commit carries its `cherry picked from commit <sha>`
marker. A matching title is advisory only (`title-match (advisory)`); it never
skips a row on its own.

- `ALREADY_APPLIED`: present by that rule; skip, or record an explicit
  manifest decision to pick it again.
- `NOT_MERGED`: record `Skipped/NOT_MERGED`, continue independent rows, and
  report it; never auto-pick an unmerged head.
- `NEEDS_INVESTIGATION`: run investigate/gate.
- `PREFLIGHT_BLOCKED`: missing PR, unknown SHA, unfetched merge commit, or a
  `gh`/git failure.

The `parents` column is the source commit's parent count: 2 or more is a merge
commit ([apply.md](apply.md)). Do not spend model work re-discovering facts
already in the table.

## Ordering

Run `<skill-dir>/scripts/batch-deps.sh --source <source-branch> --target
<target-branch> <sha>...` over the `NEEDS_INVESTIGATION` rows. It lists each
SHA's files (a merge against its first parent), the pairs sharing files, the
order by position on the source branch's first-parent line, and the fully
independent SHAs.

- Build the graph from shared-file pairs and sort topologically in
  first-parent order.
- That order is valid only if no later commit reverts or replaces what an
  earlier one touched. Inspect each pair where the later commit is a
  `revert`, `chore: remove` or `refactor` of the earlier one's code, and swap
  them when the hunks allow: if A modifies file F and B later removes it,
  applying B first lets A apply against the post-removal state. Merge order
  never shows this; only file overlap does.
- Flag circular dependencies or ambiguous prerequisite chains for a user
  decision.
- Independent rows may be investigated in parallel, by the parent or one
  `aitk-debugger` agent per independent island; application on the target
  stays sequential.

## Manifest and Waves

For 10+ changes, or any run with meaningful dependencies, expected conflicts
or several intervention points, keep `CHERRY_PICK.md` from
[the manifest template](../templates/cherry-pick-manifest.md); it is the only
row schema and holds the handoff format (Subagent Handoffs). `PROJECT.md`
points only to the target branch, current phase, next wave and manifest path.
Never commit `CHERRY_PICK.md`; keep it ignored at the workspace root, update it
before every checkpoint, and resume from its active row or wave.

Group rows into waves. Prefer small waves, down to one row, when conflicts,
shared files, dependency manifests, migrations, generated files or API-shape
changes appear, and for dependency chains; larger waves only for independent,
cheaply validated backports. Wave size never weakens per-cherry validation or
the per-cherry push.

## Execution

1. `ALREADY_APPLIED`, `NOT_MERGED` and `PREFLIGHT_BLOCKED` rows get no
   workers.
2. Run the full single-cherry flow for each row. Mutating work runs in an
   isolated worktree or returns patch-only output; context isolation alone is
   not filesystem isolation.
3. Replay any isolated result onto the live target branch in order, then rerun
   the scope audit and the assigned validation there before marking it
   `Applied` or pushing.
4. Fill each row's Push cell before starting a dependent row; stop dependent
   rows after a failure or a pending push, while independent rows continue.
5. Workers never own shared-branch ordering or the push.
6. Surface escalations and produce one final report covering pushed and
   pending cherries.

With `--plan-only`, run pre-flight, ordering and per-cherry investigate/gate,
and produce the table without applying anything.

## Headless Mode (experimental)

A TRIVIAL, independent row may run on the native implementer agent
(`aitk-implementer`) headless. Validate the mode on one cherry in a repo before
fanning out. Preconditions: no dependency chain, shared API, migration,
generated file, auth, routing or lockfile risk; an isolated worktree or clone,
or patch-only output; target, source SHA, validation expectation and output
path recorded in `CHERRY_PICK.md`; for a merge commit, pre-flight confirmed
parent 1 is the target-base side, otherwise `Blocked: merge parent ambiguous`.
Any conflict returns `Blocked: conflict`; headless mode never adapts. A
headless result is a candidate, not success: step 3 above still applies.
