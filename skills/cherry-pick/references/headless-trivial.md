---
tier: Standard
---

# Headless Trivial Cherry-Pick Contract

Use only for TRIVIAL, independent cherry-picks after batch pre-flight, sequence planning, and gate classification have already completed.

This is an experimental execution mode for short-lived headless workers. Validate it on one cherry in a repo before fanning out.

## Preconditions

- Gate difficulty is `TRIVIAL`.
- No dependency chain, shared API, migration, generated file, auth, routing, or lockfile risk.
- Worker runs in an isolated worktree/separate clone, or returns patch-only output. A plain branch in a shared checkout is not isolation for applying work.
- The orchestrator has recorded the target branch, source SHA, validation expectation, and output path in `CHERRY_PICK.md`.
- If the source SHA is a merge commit, pre-flight has verified it is the PR merge commit and parent 1 is the target-base side. Otherwise headless mode must stop as `Blocked: merge parent ambiguous`.
- The worker is not authorized to mutate the shared target branch or push unless the orchestrator explicitly grants that boundary for this run.

## Worker Task

1. Check out the assigned isolated worktree/separate clone, or prepare patch-only output without mutating the shared checkout.
2. Detect whether the source SHA is a merge commit. For ordinary commits run `git cherry-pick -x <source-sha>`. For merge commits, run `git cherry-pick -x -m 1 <source-sha>` only when the precondition above is recorded; otherwise stop as `Blocked: merge parent ambiguous`.
3. If conflicts occur, stop and return `Blocked: conflict`; do not adapt in headless mode.
4. Run the mandatory scope audit from `validate.md`.
5. Run the assigned validation command(s), or record why they could not run.
6. Return exactly one compact status block.

The worker may not report `Result: Applied` unless scope-audit evidence is present. The orchestrator must reject an `Applied` status without:
- literal `scope-audit.sh` output pasted in the status block
- per-hunk audit verdict summary
- final `LEAK / CLEAN / ESCALATE` recommendation

Headless success is a candidate result, not final shared-branch success. The orchestrator must apply the worker's resulting commit or patch onto the live target branch in planned order, rerun the mandatory scope audit and minimum assigned validation on that live branch, then perform any authorized push itself and emit the `## Push Boundary — <pr-or-sha>` block (see SKILL.md step 8) **before** dispatching the next headless worker.

## Status Block

```markdown
## Status
PR/SHA:
Result: Applied | Blocked | Skipped
Target branch/worktree:
Target SHA:
Scope audit: CLEAN | LEAKED-REVERTED | ESCALATED | NOT-RUN
Scope audit evidence:
- scope-audit.sh: <literal output>
- hunk verdicts: <compact summary>
- recommendation: LEAK | CLEAN | ESCALATE
Validation: Tested | Checked | Build-only | Structural | Not run
Commands run:
Residual risk:
Next action for orchestrator:
```

Do not include full diffs, long logs, or reasoning transcripts. If blocked, include the shortest decisive evidence and any local file path that contains the raw output.
