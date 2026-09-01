---
name: cherry-pick
description: Cherry-pick, backport, or apply commits/PRs onto another branch with safety gates and per-change validation; also release audits — "what's on master that hasn't reached the release branch", finding backport candidates. Do NOT use for same-branch bug fixes, broad refactors, dependency upgrades, or general behavior rewrites.
---

# Cherry-Pick

Safely move one or more isolated changes (bug fixes, isolated features) onto a target branch.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `cherry-pick`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Authorization Boundary

Authorization mode: `invocation`. Per-cherry push is the default action once
validation passes — invoking `cherry-pick` is itself the authorization,
subject to the per-cherry push confirmation block. `--no-push` opts out:
validate locally and record `pending-authorization` instead of pushing.

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present. Cherry-picking has a small set of recurring failure modes; do not relearn them.

Read `rules/gates.md` — its six-state contract (`PASS`/`RETRY`/`ESCALATE`/
`USER_DECISION`/`BLOCKED`/`RECLASSIFY`) is the vocabulary every checkpoint
below translates into; the checkpoints keep their own domain-specific
verdicts and block formats (Gate Decision, Scope Audit, Push Boundary — this
skill's execution table and `CHERRY_PICK.md` remain its state artifact, not
`PROJECT.md`, per the Notes section below) rather than being rewritten
against `rules/gates.md`'s block format verbatim. Where a checkpoint's
outcome is a real command's exit status — the Single Cherry-Pick Flow's step
7b pre-commit/build/type-check/test run — that portion follows
`skills/verification-loop`'s
run-command-and-decide-RETRY-vs-ESCALATE shape (fix, re-run, and escalate
only if the *same* check fails twice in a row) rather than looping
indefinitely; it is cited, not re-run through that skill's `aitk gate-state`
persistence, since this skill does not own `PROJECT.md`.

## Contract

**In scope:** classify each change, plan its application, apply, adapt conflicts when source intent can be preserved, run repo-standard validation.

**Out of scope:** broad refactors, behavior-changing adaptations without approval, dependency reinstall or environment rebuild, forcing incompatible APIs onto the target.

**Success criteria:** each change is classified `Applied | Partial | Blocked | Rejected | Skipped`; applied changes preserve source intent; validation status recorded; push status recorded; batch state lives in the execution table or `CHERRY_PICK.md`; PROJECT.md is updated by the parent workflow (this skill does not own it).

If the workflow would cross a contract boundary, stop and ask — do not cross first and report after.

Per-cherry push is the default action at the Single Cherry-Pick Flow's step 8 — every successfully validated cherry is pushed to the target branch before the next cherry starts. `--no-push` opts out: validate locally, record `pending-authorization`, and stop before publishing. The per-cherry push boundary (step 8) and its hard-gate confirmation block still run on every cherry regardless; `--no-push` only changes whether the boundary's outcome is `pushed` or `pending-authorization`.

For STANDARD/COMPLEX or expensive cherry-picks, follow
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

Each cherry-pick runs eight validation phases in order — investigate, gate,
plan, plan review, apply, adapt, validate (scope-leak audit, correctness
validation, and conditional unblock discovery / blocked-owner notification),
then a per-cherry push boundary. No phase may be skipped — the scope-leak
audit in step 7a is the only defense against scope leak and is mandatory on
every cherry, including clean applies. Registers dispatch boundaries
`cherry-pick.scope-leak-review`, `cherry-pick.scope-leak-rereview`, and
`cherry-pick.unblock-discovery`.

→ Full procedure: [references/single-cherry-pick-flow.md](references/single-cherry-pick-flow.md)

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
- `complexity`: from gate (`trivial` / `standard` / `complex`); use `standard` for batch
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
