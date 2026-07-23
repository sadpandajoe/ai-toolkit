# Batch Cherry-Pick Flow

When multiple PRs/SHAs are provided, the main agent acts as a **thin
orchestrator**. It owns ordering, dependency tracking, user decisions,
checkpoint boundaries, and final synthesis. It must not accumulate raw
per-cherry context.

**Invariant: each cherry must start with clean context.** Use isolation that
prevents cherry N from inheriting earlier diffs and decisions.

## Deterministic Batch Pre-Flight

Before deep investigation, run a deterministic pre-flight over the full list
and write compact results into `CHERRY_PICK.md`. Put any unavoidable raw
sidecar under a workspace-local ignored path and reference it from the manifest.

Gather, when applicable:

- PR title, merge state, merge commit, and base/head refs
- source SHA(s) resolved from PRs
- already-applied evidence on the target branch, preferring exact `-x` markers;
  PR number/title matches are advisory without source-SHA evidence
- obvious not-merged or missing-merge-commit cases
- touched files and overlap signals for dependency ordering

Sort rows into:

- `ALREADY_APPLIED` — skip only with exact source-SHA evidence or an explicit
  manifest decision
- `NOT_MERGED` — record `Skipped/NOT_MERGED`, continue independent rows, and
  report it; never auto-pick an unmerged head
- `NEEDS_INVESTIGATION` — run investigate/gate
- `PREFLIGHT_BLOCKED` — missing PR, target, auth, or unambiguous source

Do not spend model work re-discovering facts already in the pre-flight table.

## Durable Batch Manifest

For 10+ changes, or any run with meaningful dependencies, expected conflicts,
or several intervention points, create or update local `CHERRY_PICK.md` from
[the manifest template](../templates/cherry-pick-manifest.md).

`PROJECT.md` points only to the target branch, current phase, next wave, and
manifest path. `CHERRY_PICK.md` owns the execution table, waves, dependencies,
per-cherry validation, conflicts, user decisions, and compact handoffs.

Keep rows short (no more than three lines per cell). Store no full diffs, raw
logs, or worker transcripts. Never commit `CHERRY_PICK.md`; keep it ignored at
the workspace root. Update it before every checkpoint/reset and resume from its
active row or wave rather than chat history.

## Wave Size Policy

Wave size never weakens per-cherry validation or publish authorization.

| Case | Wave size |
|------|----------:|
| Tiny independent fixes | 5 |
| Normal bug fixes | 3 |
| Cross-cutting changes | 1 |
| Expected conflicts | 1 |
| Dependency chain | 1 sequentially |
| Clean mechanical backports | 5-8 only if validation is cheap |

Investigate, gate, or plan independent changes in parallel when useful. Apply
on the target branch in dependency-safe sequence unless isolated worktrees and
an explicit fan-in plan make parallel mutation safe.

## Worker Handoff Contract

Each per-cherry or per-wave worker returns only:

- PR/SHA and source commit(s)
- target commit SHA after apply
- result: `Applied` / `Partial` / `Blocked` / `Rejected` / `Skipped`
- conflicts: `none` or a compact summary
- scope audit: `CLEAN` / `LEAKED-REVERTED` / `ESCALATED`
- validation label: `Tested` / `Checked` / `Build-only` / `Structural` / `Not run`
- push status: `pushed` / `pending authorization` / `deferred by request`
- commands run, residual risk, and dependency implications
- unblock candidates for blocked/rejected rows, or `none` with a reason

No full diffs or long logs unless blocked. Point to evidence paths or return the
shortest decisive excerpt.

## Execution

1. Run [batch sequence planning](batch-sequence.md).
2. Dispatch after pre-flight and per-cherry gating:
   - `ALREADY_APPLIED`, `NOT_MERGED`, and `PREFLIGHT_BLOCKED` get no workers.
   - TRIVIAL scope audits use `review`; NON-TRIVIAL audits use `deep-review`.
   - Every other worker uses the stable route at its inventoried dispatch
     marker; difficulty never selects an undeclared model tier.
   - Mutating workers use isolated worktrees/branches or return patch-only
     output. Headless application is limited to TRIVIAL, independent rows with
     the [headless contract](headless-trivial.md).
3. Run the full single-cherry flow for each row. Replay any isolated result onto
   the live target branch in order, then rerun scope audit and assigned
   validation before marking it Applied or pushing.
4. Emit the per-cherry push-boundary block before dispatching a dependent row.
   Stop dependent work when push is pending or deferred; independent islands
   may continue.
5. Keep status in the execution table or manifest. Stop dependent rows after a
   failure; independent rows may continue.
6. Surface escalations and produce a final report covering both pushed and
   pending cherries.

Workers never own final shared-branch ordering or push unless a run-specific
grant says so. Context isolation alone is not filesystem isolation.

With `--plan-only`, run sequence plus per-cherry investigate/gate and produce
the execution table without applying changes.
