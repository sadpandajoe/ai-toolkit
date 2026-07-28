---
name: cherry-pick
description: Cherry-pick, backport, or apply commits/PRs onto another branch with safety gates and per-change validation; also release audits — "what's on master that hasn't reached the release branch", finding backport candidates. Do NOT use for same-branch bug fixes, broad refactors, dependency upgrades, or general behavior rewrites.
---

# Cherry-Pick

Safely move one or more isolated changes (bug fixes, isolated features) onto a target branch.

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present. Cherry-picking has a small set of recurring failure modes; do not relearn them.

## Contract

**In scope:** classify each change, plan its application, apply, adapt conflicts when source intent can be preserved, run repo-standard validation.

**Out of scope:** broad refactors, behavior-changing adaptations without approval, dependency reinstall or environment rebuild, forcing incompatible APIs onto the target.

**Success criteria:** each change is classified `Applied | Partial | Blocked | Rejected | Skipped`; applied changes preserve source intent; validation status recorded; push status recorded; batch state lives in the execution table or `CHERRY_PICK.md`; PROJECT.md is updated by the parent workflow (this skill does not own it).

If the workflow would cross a contract boundary, stop and ask — do not cross first and report after.

Per-cherry push is the default action at step 8 — every successfully validated cherry is pushed to the target branch before the next cherry starts. `--no-push` opts out: validate locally, record `pending-authorization`, and stop before publishing. The per-cherry push boundary (step 8) and its hard-gate confirmation block still run on every cherry regardless; `--no-push` only changes whether the boundary's outcome is `pushed` or `pending-authorization`.

For non-trivial or expensive cherry-picks, follow
`rules/context-management.md`: checkpoint and apply `context_reset` after
investigate/gate/plan is recorded, and again after apply/adapt/validate when
push authorization and final reporting remain. Batch runs reset between waves.

## Usage

```
cherry-pick <pr-url>                          # From a PR
cherry-pick <sha>                             # Single commit
cherry-pick <sha> --target <branch>           # Specific target branch
cherry-pick <sha> --force                     # Override reject-category gate
cherry-pick <sha-1> <sha-2> <sha-3>           # Batch
cherry-pick <sha-1> <sha-2> --plan-only       # Plan without applying
cherry-pick <sha-1> <sha-2> --no-push         # Validate locally; stop with push recommendation
```

## Release Audit (Candidate Discovery)

For "what's on `<source>` that hasn't reached `<release-branch>`?" questions — run the audit *before* building any cherry list. Compare **first-parent PR merges only** (never raw full-history logs), treat already-applied claims as proven only by target-side PR-number matches or exact `-x` markers, and verify every candidate with `gh pr view` before queuing.

→ Methodology + script: [references/release-audit.md](references/release-audit.md) (`scripts/release-audit.sh`)

The audit produces candidates, not decisions — every queued row still runs the full investigate/gate flow below.

## Single Cherry-Pick Flow

Each cherry-pick runs all validation phases. No validation phase may be skipped — the diff audit in step 7 is the only defense against scope leak (see gotchas.md). Step 7c runs only when the cherry terminates as `Blocked` or `Rejected`; it surfaces the upstream PRs that would unstick the row before the final report. Step 8 is a publish boundary: per-cherry push is the default; `--no-push` (or explicit user deferral during the run) records `pending-authorization` instead.

### 1. Investigate

Source analysis, target compatibility scan, prerequisite scan, **target-affected scan** (is the bug even live on target, or does it only occur on master?). Investigation produces raw analysis only — the gate decides go/no-go.

→ Full procedure: [references/investigate.md](references/investigate.md)
→ Output template: [assets/investigation-template.md](assets/investigation-template.md)

### 2. Gate

Decide should-we-cherry against the accept/reject matrix (see [references/gate.md](references/gate.md)), classify difficulty (TRIVIAL vs NON-TRIVIAL), and select the stable route for the post-apply scope audit.

`--force` overrides reject decisions only — it does not skip downstream phases.

→ Full decision matrix: [references/gate.md](references/gate.md)

### 3. Plan (main thread)

Per-cherry application strategy: file include/exclude, conflict forecast, adaptation strategy, validation approach.

Plan on the main thread for both difficulty classes. The gate-selected worker
route applies to the independent scope audit in step 7a, not to parent-session
planning.

→ Full procedure: [references/plan.md](references/plan.md)
→ Output template: [assets/plan-template.md](assets/plan-template.md)

### 4. Plan Review (main thread)

Review against investigation. Cycle back with feedback if needed. Repeat until approved.

### 5. Apply

```bash
git checkout <target-branch>
git cherry-pick -x <commit-hash>
```

Always `-x` to preserve source reference. For merge commits, add `-m 1`. For modify/delete conflicts, resolve with `git rm`, not by reverting.

→ Full escalation ladder, modify/delete handling, CHERRY_PICK_HEAD recovery: [references/apply.md](references/apply.md)

### 6. Adapt (non-trivial only)

Resolve conflicts surgically. **Never** use `git checkout --theirs` or `--ours` (see gotchas.md).

If a trivial change unexpectedly hits conflicts, escalate to adapt — the gate classification was wrong.

→ Conflict classification, scope leak detection during resolution, escalation triggers: [references/adapt.md](references/adapt.md)

### 7. Validate

Two distinct jobs, run on different threads:

**7a. Scope-leak audit — subagent, mandatory, every cherry, no exceptions.**

<!-- aitk-model-route:cherry-pick.scope-leak-review -->
Post-apply, spawn a subagent on `review` for trivial or `deep-review` for non-trivial changes. Its only job is leak detection. Single rule: every cherry, every time, including clean applies — clean applies are the highest-risk vector for scope leak.

The subagent must:
1. Resolve this skill's installed directory as `<skill-dir>`, run `<skill-dir>/scripts/scope-audit.sh <source-commit>`, and capture the literal output.
2. Run the LLM hunk-level audit comparing source diff vs cherry-pick result diff.
3. Return a structured report containing the literal `scope-audit.sh` output, per-hunk verdict, and a clear `LEAK / CLEAN / ESCALATE` recommendation.

The subagent contract, LLM audit procedure, and status labels live in [references/validate.md](references/validate.md).

<!-- aitk-model-route:cherry-pick.scope-leak-rereview -->
The orchestrator may not mark a cherry `Applied` without this report. If the subagent finds leaks, revert leaked hunks and amend on the main thread, then re-spawn the subagent on the same `review`/`deep-review` route on the amended commit.

**7b. Correctness validation — main thread.**

Conflict-marker scan, **pre-commit on changed files**, build, type-check, targeted tests. Pre-commit is mandatory — conflict resolution often re-indents lines past length limits, and pre-commit is what CI runs. If pre-commit auto-fixes or you make manual fixes, `git commit --amend --no-edit` before pushing. Do not push, then amend, then force-push.

→ Full procedure (subagent contract, LLM audit, validation order, status labels, dependency manifest rule): [references/validate.md](references/validate.md)

### 7c. Unblock Discovery (Blocked / Rejected only)

<!-- aitk-model-route:cherry-pick.unblock-discovery -->
When a cherry terminates as `Blocked` or `Rejected` for reasons that look like "target is missing something" (modify/delete, prerequisite commits flagged in investigate, target-side architecture missing), spawn a discovery subagent on `review` before moving to the final report. Its only job is to name the upstream PRs/commits that would unstick this cherry — it does **not** investigate, gate, plan, or apply them.

Skip when the rejection is intrinsic (reject-category API rewrite, dependency-bump PR, build-system change). Record "no unblock path" on the row and continue.

Mode is inform-only: surface candidates in the final report under "What to do next" so the user decides whether to add them to the run. Auto-picking is a future extension (`--auto-unblock`).

The discovery subagent must **measure** each candidate (`gh pr view --json changedFiles,additions,files`, detect `migrations/versions/`) and rate the chain's difficulty `easy | heavy | risky` — a candidate with a DB migration or a large feature PR is `risky`/`heavy`, never a bare line in a PR list. Inform-only does not mean cost-free: the offer must carry how hard it is to unblock, so a heavy chain never reads as "two quick cherries and we're in."

→ Full subagent contract, output block, future-auto-unblock notes: [references/unblock-discovery.md](references/unblock-discovery.md)

### 7d. Blocked-Owner Notification (release-candidate stories only)

When the cherry comes from a Shortcut story labeled `release-candidate` and we did **not** land it this pass (`Skipped`, `Blocked`, or `Rejected`), the decision to leave it off / force it / adapt it belongs to the person who added the `release-candidate` label, not to us. Post one comment on the story that mentions that person and hands them a clean decision: why it's blocked, how to unblock it (from 7c), our recommendation, and the options — then let them decide. We recommend; the labeler decides. Do not force-backport or adapt off our own recommendation without their reply.

Find the decider via `stories-get-history` (the entry whose `changes.label_ids.adds` contains label id `78270`), and mention them with the link form `[@handle](shortcutapp://members/<id>)` so the notification actually fires — plain `@handle` text does not notify.

Skip only when there's nothing to decide (merge SHA already on the branch, or no merged apache/superset PR exists).

→ Five required elements, decider-lookup, mention syntax, comment template: [references/blocked-owner-comment.md](references/blocked-owner-comment.md)

### 8. Per-Cherry Push (default)

```bash
git push
```

Per-cherry push is the default. Immediately after step 7 passes for *this* cherry, the orchestrator pushes — before starting the next cherry. Do not batch pushes at the end of a multi-cherry run.

`--no-push` opts out: skip the `git push`, record `Push: pending authorization` in the execution table or `CHERRY_PICK.md`, and continue to independent planning/investigation work only if it does not depend on the unpublished cherry being on the remote.

**Why per-cherry, not batched:** CI can attribute each cherry independently only when each push is per cherry. Batching defeats per-cherry attribution and forces bisection later. The user may explicitly ask for batched push (e.g., to reduce CI cost) — that request is itself the authorization: defer without re-confirming and record the batched-push decision. Agent-initiated batching remains forbidden by the push-boundary hard gate below.

**Hard gate — per-cherry push boundary.** After step 7 passes and before any subsequent work runs (next cherry's investigate/apply, final report, checkpoint, or PR creation), the orchestrator must emit this confirmation block verbatim for *this* cherry:

```markdown
## Push Boundary — <pr-or-source-sha>
Local SHA: <sha after validate/amend>
Status: pushed | pending-authorization | deferred-by-user
Remote SHA: <sha visible on remote after push> | n/a
Reason (if not pushed): <one line>
```

If `Status: pushed`, the `git push` for this cherry has already happened — not queued, not deferred. If `Status: pending-authorization` (only when `--no-push` is set) or `deferred-by-user`, the orchestrator must also stop dependent follow-ups until the user clears the boundary. Do not start the next dependent cherry's worker without this block in chat for the previous cherry. This is the only structural defense against falling into the "apply, validate, next, …, done, push" rhythm that batches pushes (see gotchas.md, "Push batched at end instead of per-cherry").

## Batch Cherry-Pick Flow

For multiple PRs or SHAs, follow [references/batch.md](references/batch.md).
That reference owns deterministic pre-flight, durable manifest, wave sizing,
worker handoffs, fan-in, and `--plan-only` behavior. The single-change safety
and per-cherry push boundaries above still apply to every row.

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
- `worker_usage`: subagent/worker invocation counts when applicable

## Continuation Checkpoint

Phases: investigate / gate / plan / plan-review / apply / adapt / validate / push-authorization / document

State to checkpoint:
- Target branch
- Current execution table snapshot
- Pending intervention points

## Notes

- **PROJECT.md**: branch-movement operations — the parent workflow owns any PROJECT.md update, not this skill.
- Always use `cherry-pick -x` to preserve source reference.
- `--force` overrides the gate's accept/reject only, never downstream phases.
- When in doubt, reject.
