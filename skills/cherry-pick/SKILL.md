---
name: cherry-pick
description: Use when the user asks to cherry-pick, backport, port a fix, or apply commits/PRs onto another branch. Covers safety gates, scope-leak detection, adaptation, and per-change validation. Do NOT use for ordinary same-branch bug fixes, broad refactors, dependency upgrades, or behavior-changing rewrites without an explicit cross-branch move.
argument-hint: "[pr-url | sha...] [--target branch] [--force] [--plan-only]"
allowed-tools: Bash(git *) Bash(gh *) Read Grep Glob Edit
---

# Cherry-Pick

Safely move one or more isolated changes (bug fixes, isolated features) onto a target branch.

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present. Cherry-picking has a small set of recurring failure modes; do not relearn them.

## Contract

**In scope:** classify each change, plan its application, apply, adapt conflicts when source intent can be preserved, run repo-standard validation.

**Out of scope:** broad refactors, behavior-changing adaptations without approval, dependency reinstall or environment rebuild, forcing incompatible APIs onto the target.

**Success criteria:** each change is classified `Applied | Partial | Blocked | Rejected | Skipped`; applied changes preserve source intent; validation status recorded; PROJECT.md updated by the parent workflow (this command does not own it).

If the workflow would cross a contract boundary, stop and ask — do not cross first and report after.

## Usage

```
/cherry-pick <pr-url>                          # From a PR
/cherry-pick <sha>                             # Single commit
/cherry-pick <sha> --target <branch>           # Specific target branch
/cherry-pick <sha> --force                     # Override reject-category gate
/cherry-pick <sha-1> <sha-2> <sha-3>           # Batch
/cherry-pick <sha-1> <sha-2> --plan-only       # Plan without applying
```

## Single Cherry-Pick Flow

Each cherry-pick runs all 7 phases. No phase may be skipped — the diff audit in step 7 is the only defense against scope leak (see gotchas.md).

### 1. Investigate (Opus)

Source analysis, target compatibility scan, prerequisite scan. Investigation produces raw analysis only — the gate decides go/no-go.

→ Full procedure: [references/investigate.md](references/investigate.md)
→ Output template: [assets/investigation-template.md](assets/investigation-template.md)

### 2. Gate

Decide should-we-cherry against the accept/reject matrix (see [references/gate.md](references/gate.md)), classify difficulty (TRIVIAL vs NON-TRIVIAL), pick model tier for plan/validate phases.

`--force` overrides reject decisions only — it does not skip downstream phases.

→ Full decision matrix: [references/gate.md](references/gate.md)

### 3. Plan (model from gate)

Per-cherry application strategy: file include/exclude, conflict forecast, adaptation strategy, validation approach.

For non-trivial changes, run plan as a subagent so the review in step 4 gets a fresh perspective. For a single trivial cherry-pick, inline planning on the main thread is fine — the gate already classified low risk.

→ Full procedure: [references/plan.md](references/plan.md)
→ Output template: [assets/plan-template.md](assets/plan-template.md)

### 4. Plan Review (main thread)

Review against investigation. Cycle back with feedback if needed. Repeat until approved.

### 5. Apply (Opus)

```bash
git checkout <target-branch>
git cherry-pick -x <commit-hash>
```

Always `-x` to preserve source reference. For merge commits, add `-m 1`. For modify/delete conflicts, resolve with `git rm`, not by reverting.

→ Full escalation ladder, modify/delete handling, CHERRY_PICK_HEAD recovery: [references/apply.md](references/apply.md)

### 6. Adapt (Opus — non-trivial only)

Resolve conflicts surgically. **Never** use `git checkout --theirs` or `--ours` (see gotchas.md).

If a trivial change unexpectedly hits conflicts, escalate to adapt — the gate classification was wrong.

→ Conflict classification, scope leak detection during resolution, escalation triggers: [references/adapt.md](references/adapt.md)

### 7. Validate

Two distinct jobs, run on different threads:

**7a. Scope-leak audit — subagent, mandatory, every cherry, no exceptions.**

Post-apply, spawn a subagent (model from gate: Sonnet for trivial, Opus for non-trivial). Its only job is leak detection. Single rule: every cherry, every time, including clean applies — clean applies are the highest-risk vector for scope leak.

The subagent must:
1. Run `${CLAUDE_SKILL_DIR}/scripts/scope-audit.sh <source-commit>` and capture the literal output.
2. Run the LLM hunk-level audit comparing source diff vs cherry-pick result diff.
3. Return a structured report containing the literal `scope-audit.sh` output, per-hunk verdict, and a clear `LEAK / CLEAN / ESCALATE` recommendation.

The orchestrator may not mark a cherry `Applied` without this report. If the subagent finds leaks, revert leaked hunks and amend on the main thread, then re-spawn the subagent on the amended commit.

**7b. Correctness validation — main thread.**

Conflict-marker scan, **pre-commit on changed files**, build, type-check, targeted tests. Pre-commit is mandatory — conflict resolution often re-indents lines past length limits, and pre-commit is what CI runs. If pre-commit auto-fixes or you make manual fixes, `git commit --amend --no-edit` before pushing. Do not push, then amend, then force-push.

→ Full procedure (subagent contract, LLM audit, validation order, status labels, dependency manifest rule): [references/validate.md](references/validate.md)

**Push after each successful cherry-pick** so CI runs against the change:
```bash
git push
```

## Batch Cherry-Pick Flow

When multiple PRs/SHAs are provided, the main agent acts as a **thin orchestrator**. It must not accumulate per-cherry context.

**Invariant: each cherry must start with clean context.** Subagents are the usual mechanism, but any isolation that prevents cherry #10 from inheriting cherry #1's diffs and decisions works. What matters is that the agent working on cherry N does not carry state from cherries 1..N-1.

1. **Sequence planning** — run [references/batch-sequence.md](references/batch-sequence.md) to determine execution order based on dependencies. Sonnet is sufficient.
2. **Per-cherry execution** — for each cherry in sequence, run the full single flow (steps 1–7) in an isolated context.
3. **Status tracking** — record results in the execution table. If one fails, do NOT continue with subsequent dependent picks. Independent picks may continue.
4. **Escalation** — surface escalations to the user, relay answers back.
5. **Final report** — collect results and produce the document phase output.

**Why isolation matters:** with 15 cherry-picks, inline processing pollutes context with prior diffs by cherry #10. Quality degrades silently — conflicts start looking alike, decisions bleed across cherries.

**`--plan-only`:** run sequence + per-cherry investigate + gate (parallel where independent). Produce execution table without applying.

## Final Report

Use the format in [examples/final-report.md](examples/final-report.md). Lead with the ticket outcome (what the user cares about), then the execution table, then actionable residuals.

The full 13-column execution table format is in [examples/execution-table.md](examples/execution-table.md). The compact table replaces it only in the final report.

**Record metrics**: include `metrics-emit` context with:
- `command`: `cherry-pick`
- `complexity`: from gate (`trivial` / `non-trivial`); use `standard` for batch
- `status`: aggregate result (`clean` if all Applied, `blocked` if any Blocked/Rejected requiring intervention, etc.)
- `rounds`: total plan-review iterations across all cherries (0 if all clean)
- `gate_decisions`: `{ verdict: PROCEED | REJECT | FORCE-PROCEED, batch_size: <N> }`
- `scope_audit`: per-cherry verdicts from the 7a subagent — `{ clean: <N>, leaked_reverted: <N>, escalated: <N> }`. Single cherry: one of `CLEAN | LEAKED-REVERTED | ESCALATED`.
- `models_used`: subagent model invocation counts

## Continuation Checkpoint

Phases: investigate / gate / plan / plan-review / apply / adapt / validate / document

State to checkpoint:
- Target branch
- Current execution table snapshot
- Pending intervention points

## Notes

- **PROJECT.md**: branch-movement operations — the parent workflow owns any PROJECT.md update, not this command.
- Always use `cherry-pick -x` to preserve source reference.
- `--force` overrides the gate's accept/reject only, never downstream phases.
- When in doubt, reject.
