---
tier: Heavy
---

# Cherry-Pick Adapt

Use when a cherry-pick cannot be applied mechanically.

## Goal

Preserve the source change's behavior on the target branch without widening scope.

This phase owns code-level adaptation only. Do not redo batch ordering or final validation here.

## Conflict Classification

Classify each conflict before editing:

- **modify/delete** — file exists on source but not target. Resolve with `git rm` in the apply phase, not here. If adapt receives these, hand back to apply.
- import or module path mismatch
- target API mismatch
- structural drift
- logic overlap
- missing prerequisite change

## Resolution Matrix (quick reference)

| Conflict type | Check | Safe resolution | Risky resolution |
|---------------|-------|-----------------|------------------|
| Import | Module exists on target? | Keep target | Accept source wholesale |
| API | Signature compatible? | Adapt to target | Force source signature |
| Test fails | What did the test expect? | Meet the expectation | Change the test |
| Structure | Can you extract just the logic? | Take functional change only | Force structural change |

## Parallel Work

When there are multiple conflicting files and they are independent, resolve in parallel with one worker per file.

Do not parallelize if:
- multiple files participate in the same behavioral change
- a shared interface or type must be updated consistently across files
- one file's resolution depends on another's outcome

## Resolution Rules

- Prefer adapting to the target branch's APIs over pulling in structural changes
- Extract only the functional part of a mixed commit when possible
- If a prerequisite change is truly required, stop and escalate — do not silently pull it in
- Reject the cherry-pick if preserving source intent would require a broad refactor
- Record adaptation severity as `None`, `Minor`, `Medium`, or `High` (see [plan.md](plan.md)). When dropping significant chunks, use `High` — not `Minor`.
- **Never use `git checkout --theirs` or `git checkout --ours`** — in cherry-pick context these take the full file from one side, silently discarding the other's changes. See [../gotchas.md](../gotchas.md). Always resolve by reading markers and editing surgically.

## Residual Bug Surfacing

When a bug-fix cherry-pick is rejected or has significant portions dropped due to architecture mismatch:

1. Assess whether the underlying bug likely exists on the target branch via a different code path.
2. If yes, surface it as a residual risk item in the Detailed Notes — not buried in adaptation notes, but called out as an actionable item (e.g., "the encoding bug likely affects the target branch via `ExecuteSqlCore` — needs a separate fix").
3. The cherry-picking rules say "validate bug exists in target branch." That validation doesn't end when the fix is rejected — the bug's existence is still the user's problem.

See [../gotchas.md](../gotchas.md) for the dropped-fix failure mode.

## Scope Leak Detection During Resolution

Conflict resolution is the primary active-vector for **scope leak** — where changes from adjacent commits on the source branch silently enter the cherry-pick through a resolved hunk. This is distinct from the post-apply diff audit in validate (which is defense in depth).

This happens when the source branch's version of a conflicting region includes changes from commits *other than* the one being cherry-picked. Accepting the source side wholesale (or resolving toward it) brings in those unrelated changes.

After resolving each conflicting file:

1. Get the source commit's original diff for that file:
   ```bash
   git diff <commit>^..<commit> -- <file>
   ```
2. Compare against your resolution: any lines in the resolved version that aren't in the source commit's diff and weren't already on the target branch are leak candidates.
3. If leak is detected, strip the unrelated lines and keep only the cherry-picked commit's changes adapted to the target's context.

When in doubt about whether a line belongs to the cherry-picked commit or leaked from an adjacent one:
```bash
git log --oneline <source-commit>..HEAD -- <file>
```
on the source branch to identify which commit introduced it.

## Escalation Triggers

Stop and ask for user input when:

- there are two reasonable behavior-preserving interpretations
- the adaptation changes externally visible behavior
- the target branch lacks required architectural groundwork
- dropping a bug fix leaves the underlying bug unaddressed on the target branch (surface the residual risk even if proceeding)
- scope leak detection finds changes from adjacent commits that may be intentional prerequisites
- a bundled PR contains sub-fixes that look unrelated to the main fix and would otherwise be dropped as scope creep — surface to the orchestrator with the list of sub-fixes proposed for exclusion and a one-line rationale per drop, rather than deciding alone. The user explicitly listed the PR in the batch, which generally implies they want everything in it; the orchestrator (or user) should confirm the drop, not the adapter.
