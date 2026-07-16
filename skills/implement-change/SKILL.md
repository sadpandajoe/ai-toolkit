---
name: implement-change
description: Use when implementing one approved plan or RCA slice test-first and returning verified files for review. Do NOT use for investigation, unapproved scope, planning, or standalone review.
---

# Implement Change

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Use this phase when the workflow is ready to apply a code change after investigation and any needed planning are complete.

## Required Context
Read before starting: `rules/implementation.md`, `rules/testing.md`

## Goal

Implement one slice from the plan — the narrowest change that satisfies the slice's exit criteria. Add regression protection, verify against the slice's acceptance criteria, and hand the result back.

## Slice Awareness

When the plan defines structured slices (with scope, entrance/exit criteria, acceptance), implement exactly one slice per invocation:
- Verify **entrance criteria** are met before starting — if not, stop and report what's missing
- Stay within the slice's **scope** — do not touch files outside the boundary
- Stop when **exit criteria** are met — the slice is done, hand it back
- Run the slice's **acceptance** check to verify

When no structured slices exist (simple fix, trivial path), implement the full change as a single unit.

## Worktree Mode

Default mode is the caller's current worktree. In default mode, do not commit, amend, rebase, push, or force-push. Return changed files and verification evidence only; the orchestrator owns review, durable state, and any authorized git action.

When launched through `isolated_worktree`, this skill runs in a temporary git
worktree. Key differences:

- **Dependencies may be missing**: check for `node_modules/` or equivalent before running tests. Install if needed.
- **Build outputs may be absent**: rebuild if the slice's acceptance check requires it.
- **Commit your changes**: worktree changes must be committed to be preserved. Create a commit with a clear message referencing the slice name.
- **The orchestrator handles the merge**: do not merge back yourself. Commit on the worktree's temp branch and return the implementation handoff.

## Core Steps

1. Check entrance criteria (if slice is defined). Stop if unmet.
2. Write the test(s) first per the test-first mode the plan specified (see `rules/implementation.md` Test-First Modes):
   - **RED/GREEN per slice** (bug fixes): write the failing test, run it, confirm RED.
   - **Test set as specification** (features): write the slice's full acceptance test set as the spec.
3. If test-first is blocked by repro, env, or harness constraints, write the test anyway and record the verification gap before continuing.
4. Implement the minimum code change that satisfies the slice's exit criteria (or the validated RCA for non-sliced work).
5. Run the slice's acceptance check or targeted verification for changed files.
   - For RED/GREEN: confirm the previously-failing test now passes (GREEN).
   - For test-set-as-spec: run the full set; reconcile any failures by deciding code-vs-test and noting why if a test changed.
6. Note anything that could not be verified locally.
7. Hand changed files back to the calling workflow for `review-code`.

## Output

```markdown
## Implementation Handoff

- Slice: <name, or "single change" if no slices>
- Entrance criteria: <met / N/A>
- Exit criteria: <met — evidence>
- Files changed:
  - <file>
- Branch/commit: <only when `isolated_worktree` is active; otherwise "N/A">
- Tests added or updated:
  - <test>
- Acceptance: <passed / failed / not runnable — reason>
- Unverified areas:
  - <gap or none>
```

## Orchestrator Responsibility (After Handoff)

The orchestrator owns durable state. After receiving this handoff, the calling
workflow must append its `## Slice N Complete` block to `PROJECT.md` before the
checkpoint API advances and `context_reset` fires. This is a hard gate:
context-management boundary 3 is not met until the block is written. The
selected canonical workflow reference owns the exact block shape.
