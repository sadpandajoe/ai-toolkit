---
name: workstreams-sync
description: Reference for collecting subagent results, updating slice status in PROJECT.md, merging worktree branches, and surfacing failures.
tier: Standard
---

# Sync Workstreams

After parallel implementation subagents complete, this reference owns the merge-back and status-tracking phase. It collects results, updates the slice status table, merges worktree branches in dependency order, and gates on failures before proceeding.

## Required Context

The caller provides:
- The list of subagent results (each should contain an Implementation Handoff block)
- The dependency graph from the plan (which slices depend on which)
- The current branch name

## Steps

### 1. Collect Results

Read each subagent's Implementation Handoff block. Extract for each slice:
- Slice name
- Entrance criteria status (met / N/A)
- Exit criteria status (met / unmet — with evidence)
- Files changed
- Tests added or updated
- Acceptance status (passed / failed / not runnable)
- Unverified areas

### 2. Update Slice Status Table

Write or update the slice status table in PROJECT.md:

```markdown
## Slice Status
| Slice | Status | Exit Criteria | Notes |
|-------|--------|---------------|-------|
| Slice 1: [name] | complete | met | [summary] |
| Slice 2: [name] | failed | unmet — [reason] | [what went wrong] |
| Slice 3: [name] | blocked | unmet — depends on Slice 2 | |
```

Status transitions: `queued` → `in-flight` → `complete` / `failed` / `blocked`

### 3. Gate on Failures

If any slice failed its exit criteria or acceptance check:
- **Stop before merging**. Do not merge partial results.
- Surface the failure clearly: which slice, what failed, why.
- Assess cascading impact: are other slices that depend on the failed one now blocked?
- Update dependent slices to `blocked` status.

Recommendation when failures exist: `stop-for-failure`

### 4. Merge Worktree Branches

Only proceed here if all slices are `complete`.

Merge each worktree's temp branch into the current branch:
1. Process in **dependency order** — if Slice B depends on Slice A, merge A first
2. For each merge:
   ```bash
   git merge <worktree-branch> --no-edit
   ```
3. If a merge conflict occurs:
   - **Stop immediately**. Do not auto-resolve.
   - Surface the conflict: which files, which slices overlap.
   - This means the plan's scope boundaries were wrong — files that should have been in one slice were split across two.
   - Recommendation: `stop-for-conflict`
4. After each successful merge, verify the branch is clean (`git status`)

### 5. Integration Check

After all merges complete successfully:
1. Run a quick build/type-check to verify the integrated result compiles
2. Run lint if available
3. If integration fails, surface which merge introduced the failure (bisect by merge order)

## Output

```markdown
## Workstream Sync

### Slice Status
| Slice | Status | Exit Criteria | Notes |
|-------|--------|---------------|-------|
| [name] | complete/failed/blocked | met/unmet | [details] |

### Merge Result
- Slices merged: [N of M]
- Merge conflicts: [none / list of conflicting files]
- Integration check: pass / fail / skipped

### Recommendation
proceed-to-review / stop-for-failure / stop-for-conflict / stop-for-integration-failure
```

## Notes
- This reference never auto-resolves merge conflicts. Conflicts indicate a planning error (overlapping slice scopes) that needs human judgment.
- The slice status table in PROJECT.md is the durable record — if context is cleared, the status table survives.
- When a slice fails, do not abort already-completed slices. Their work is committed on worktree branches and can be merged independently if the failed slice is re-planned.
- This reference is consumed by `create-feature` step 5b and `fix-bug` step 13, replacing inline merge logic.
