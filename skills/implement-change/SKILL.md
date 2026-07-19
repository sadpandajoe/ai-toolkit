---
name: implement-change
description: Use when implementing one approved plan or RCA slice as a bounded patch and returning changed files for parent verification and review. Do NOT use for investigation, unapproved scope, planning, or standalone review.
---

# Implement Change

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Use this phase when the workflow is ready to apply a code change after investigation and any needed planning are complete.

## Required Context
Read before starting: `rules/implementation.md`, `rules/testing.md`

## Goal

Implement one slice from the plan — the narrowest patch that satisfies the slice's exit criteria. Add regression protection and hand the result back for parent-run verification.

## Slice Awareness

When the plan defines structured slices (with scope, entrance/exit criteria, acceptance), implement exactly one slice per invocation:
- Verify **entrance criteria** are met before starting — if not, stop and report what's missing
- Stay within the slice's **scope** — do not touch files outside the boundary
- Stop when **exit criteria** are met — the slice is done, hand it back
- Name the slice's **acceptance** check for the parent to run

When no structured slices exist (simple fix, trivial path), implement the full change as a single unit.

## Worktree Mode

Default mode is the caller's current worktree. In default mode, do not commit, amend, rebase, push, or force-push. Return changed files and verification evidence only; the orchestrator owns review, durable state, and any authorized git action.

Routed model workers are patch-only and do not use `isolated_worktree`; their
contract forbids commits. Claude implementation workers are launched without
Bash, while Codex implementation workers retain sandboxed shell access for
editing and inspection. In both cases the parent orchestrator owns verification,
worktree preservation, and any authorized commit.

## Core Steps

1. Check entrance criteria (if slice is defined). Stop if unmet.
2. Write the test(s) first per the test-first mode the plan specified (see `rules/implementation.md` Test-First Modes):
   - **RED/GREEN per slice** (bug fixes): write the regression test and name the parent-run RED check.
   - **Test set as specification** (features): write the slice's full acceptance test set as the spec.
3. If test-first is blocked by repro, env, or harness constraints, write the test anyway and record the verification gap before continuing.
4. Implement the minimum code change that satisfies the slice's exit criteria (or the validated RCA for non-sliced work).
5. Return the exact acceptance and targeted verification commands for the parent.
6. Mark verification pending; never claim RED/GREEN or acceptance success from a patch-only worker.
7. Hand changed files back to the calling workflow for `review-code`.

## Output

```markdown
## Implementation Handoff

- Slice: <name, or "single change" if no slices>
- Entrance criteria: <met / N/A>
- Exit criteria: <implemented — pending parent verification>
- Files changed:
  - <file>
- Branch/commit: N/A
- Tests added or updated:
  - <test>
- Acceptance: pending parent — <exact commands>
- Unverified areas:
  - <gap or none>
```

## Orchestrator Responsibility (After Handoff)

The orchestrator owns durable state. After receiving this handoff, the calling
workflow must append its `## Slice N Complete` block to `PROJECT.md` before the
checkpoint API advances and `context_reset` fires. This is a hard gate:
context-management boundary 3 is not met until the block is written. The
selected canonical workflow reference owns the exact block shape.
