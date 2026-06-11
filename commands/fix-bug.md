# /fix-bug - End-to-End Bug Workflow

@{{TOOLKIT_DIR}}/rules/input-detection.md
@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: You have a bug report and want the repo-standard workflow to triage it, check for an existing fix, implement safely when needed, and validate the result.
> **Produces**: Triage notes, existing-fix decision, validated RCA when needed, implemented fix, Review Gate, QA validation when relevant, and a final bug-fix summary.

## Usage

```bash
/fix-bug "saving settings fails on Safari"
/fix-bug sc-12345
/fix-bug apache/superset#28456
/fix-bug https://github.com/owner/repo/issues/123
/fix-bug https://app.shortcut.com/.../story/123
/fix-bug sc-12345 --watch     # after the fix push lands on a branch with an open PR, chain into /watch-pr
```

## Command Contract

The command owns the visible gates and sequence. Each step loads only the referenced skill phase when that step starts; do not eagerly load every phase reference up front.

- Emit a Complexity Gate before investigation or implementation.
- Fetch ticket context before classification or implementation when the input is a ticket or issue.
- Run the existing-fix check unless the fix is TRIVIAL mechanical work.
- For STANDARD work, write `PLAN.md` and update PROJECT.md before implementation.
- Do not implement STANDARD work until the `PLAN.md Written` block is emitted.
- For STANDARD work, run plan-review iteration on `PLAN.md` via `skills/planning/references/iterate-review.md` after `PLAN.md Written` and before implementation; require the reviewer threshold and cold-read Go documented in that helper.
- Run `/verify` or equivalent pre-flight checks before `/review-code`, and record the result in the Review Gate.
- Do not commit without an added or updated regression test unless the gap is explicitly accepted.
- Default action when verification is STRONG, a regression test was added or updated (or the gap was explicitly accepted by the user), and the Review Gate is clean: create a new commit on the current feature branch and push it as part of the fix flow. The TDD regression test is the verification gate that makes auto-push safe — without it, pause. Pause for amend, rebase, force-push, ambiguous push target (not the current feature branch, or tracks an unexpected remote), PARTIAL/WEAK verification, or any STANDARD-path hold (RCA review, plan review, per-slice gates).
- Only the main thread writes PROJECT.md or `PLAN.md`. Subagents return handoffs; the orchestrator updates durable state.
- With `--watch`, after the final push lands on a branch with an open PR, chain into `/watch-pr` on that PR — the flag is the explicit pre-authorization for the watch's standing commit+push grant. Without the flag, when an open PR exists for the pushed branch, end the summary with a one-line `/watch-pr` suggestion instead; never enter the watch unflagged.
- For STANDARD or expensive bug work, follow `rules/context-management.md`: checkpoint/clear after RCA review accepts, after `PLAN.md` is written, after plan review accepts, after implementation, and after code review fixes when QA/PR work remains.
- For STANDARD work, emit the Phase Plan block from `rules/complexity-gate.md` immediately after the Complexity Gate.
- **`## Slice N Complete` PROJECT.md write is a hard gate** before every per-slice checkpoint/clear on the STANDARD path. Block shape matches `commands/create-feature.md` step 8. No clear without the entry.
- **`## Bug Fix Complete` PROJECT.md write is a hard gate** before the chat summary on every path. TRIVIAL/MODERATE single-shot runs need this so `/clear` or `/archive-project-file` after `/fix-bug` does not lose the result. STANDARD runs that ended with a per-slice entry must still emit the rollup before the summary. See the end-of-workflow section below.

## Planning Phase Boundary

The planning phase is a workflow boundary. For STANDARD bug fixes, automatically start it after RCA evidence is strong enough to plan. Use the platform's native planning/read-only mode when available; otherwise announce the planning phase and self-enforce the same boundary.

During the planning phase, read, search, reproduce where possible, investigate root cause, and draft the fix approach. Do not make implementation edits, change tests, run implementation workers, or start review iterations. If native planning/read-only mode cannot write files, exit that mode after drafting, then write `PLAN.md` as the planning-phase output. End by updating PROJECT.md with the active-plan pointer and emitting `PLAN.md Written`:

```markdown
## PLAN.md Written
Plan: PLAN.md
Project state: PROJECT.md updated
Next: [first fix slice or user decision]
```

TRIVIAL and MODERATE bug fixes skip the formal planning phase. If durable RCA review, plan-review iteration, or slice orchestration becomes necessary, reclassify as STANDARD.

## Bug Complexity Signals

Use these command-specific signals with `rules/complexity-gate.md`:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Root cause | Obvious from error or diff | Confirmed by focused investigation | Unknown or competing causes |
| Files touched | 1-2 | 2-4, single subsystem | 3+ across systems or unclear ownership |
| Regression risk | Mechanical/local | Contained functional fix | Cross-cutting workflow, data, auth, or migration risk |
| Repro/validation | Cheap targeted check | Targeted test or local repro | Needs RCA validation, app flow, or broad scenario validation |

MODERATE is the default for real but contained bug fixes. Use STANDARD when the fix needs durable RCA, plan-review iteration, multiple review/fix waves, or investigation lanes.

## Happy Paths

- **Trivial**: normalize input, fetch ticket context if present, emit Complexity Gate, implement inline, run smallest meaningful verification, emit Review Gate `skipped`/`micro-fix` only when the Review Gate exception applies; otherwise reclassify MODERATE.
- **Moderate**: run existing-fix scan, investigate inline, add or update a regression test when feasible, implement inline by default, run `/verify` or equivalent pre-flight checks, then one fresh `/review-code` pass.
- **Standard**: run existing-fix scan, validate RCA, run RCA review and Action Gate, write `PLAN.md`, checkpoint/clear, run plan-review iteration on `PLAN.md`, checkpoint/clear, then implement slices inline by default or with bounded subagents only when isolation or parallelism helps.

## Step Routing And Handoffs

Use the happy paths and path rules as the primary flow. Use this table as a phase lookup when entering a step; do not preload every linked route.

| Step | Owner | Route | Load / hand off when |
|------|-------|-------|----------------------|
| Normalize input | Main thread | `rules/input-detection.md` | Load immediately. Fetch ticket context before classification or implementation. |
| Complexity Gate | Main thread | `rules/complexity-gate.md` | Load immediately. Choose TRIVIAL, MODERATE, or STANDARD path. |
| Existing fix check | Main thread | [skills/debug/references/check-existing-fix.md](../skills/debug/references/check-existing-fix.md) | MODERATE/STANDARD path before planning or coding. If `FIXED_UPSTREAM`, route to `/cherry-pick`; if `FIX_PENDING_PR`, stop with choices. |
| Triage/repro | Main thread by default | [skills/qa/references/triage-bug.md](../skills/qa/references/triage-bug.md) | Load when report evidence is weak, user-visible behavior needs repro, or STANDARD path needs scenario evidence. |
| Environment prep | Main thread | [skills/preflight/references/prepare-environment.md](../skills/preflight/references/prepare-environment.md) | Load only when repro or validation needs a runnable app. |
| RCA investigation | Main thread by default; bounded investigation lanes only when causes are independent | [skills/debug/references/investigate-change.md](../skills/debug/references/investigate-change.md) | Load when root cause is not obvious. Lanes return compact evidence, candidate RCA, confidence, ruled-out alternatives, and next action. |
| RCA review | Fresh reviewer subagent | [skills/debug/references/review-rca.md](../skills/debug/references/review-rca.md), `action-gate` | STANDARD path before `PLAN.md`. Continue after material findings are resolved and the Action Gate says proceed; otherwise stop. |
| Plan review | Fresh reviewer subagents driven by the iterate-review helper | [skills/planning/references/iterate-review.md](../skills/planning/references/iterate-review.md) with reviewer set `plan-review/references/implementation.md`, `testing/references/review-testplan.md`, plus conditional `plan-review/references/architecture.md` (cross-cutting fixes), `plan-review/references/frontend.md` (UI), `plan-review/references/backend.md` (API/DB/migrations); scope `substantial`; include `action-gate` | STANDARD path after `PLAN.md Written` and before implementation. Reviews the Fix Approach and Test Strategy sections written into `PLAN.md` — the RCA review does not cover them. Continue after threshold + cold-read Go; otherwise revise `PLAN.md` and re-run failing reviewers. |
| Implementation | Main thread for trivial/tightly-coupled work; bounded subagent only for isolated slices | [skills/implement-change/SKILL.md](../skills/implement-change/SKILL.md) | Start after inline RCA for MODERATE, or after plan-review threshold + cold-read Go for STANDARD. Prompt includes root cause, scope/files, regression expectation, acceptance checks, relevant plan excerpt, branch/base. Return `Implementation Handoff`. |
| Review | `/review-code` reviewer subagents | [skills/review/references/local-review.md](../skills/review/references/local-review.md) | Run after `/verify` or equivalent pre-flight checks when repo-tracked files changed. Branch on Review Gate status. |
| QA validation | Main thread by default; QA subagent only for large independent scenario sets | [skills/qa/references/validate-fix.md](../skills/qa/references/validate-fix.md) | Load when a user-visible workflow bug changed and app is runnable. State why skipped if not runnable. |
| Summary | Main thread | [skills/reporting/templates/fix-bug-summary.md](../skills/reporting/templates/fix-bug-summary.md), `metrics-emit` when available for the workflow | End of workflow or stop point. State RCA confidence, regression test status, verification strength, Review Gate status, QA result, and residual risk. |

## Path Rules

- **Trivial**: skip existing-fix scan and formal planning; add a cheap regression assertion when possible; implement and test inline. Zero-logic diffs emit Review Gate `skipped`; true micro-fixes emit `micro-fix` only when the micro-fix rule passes. If logic review is needed beyond those exceptions, reclassify as MODERATE.
- **Moderate**: run existing-fix scan, investigate inline, add/update regression coverage when feasible, implement inline by default, run `/verify` or equivalent pre-flight checks, then one fresh `/review-code` pass.
- **Standard**: use the planning phase for investigation/RCA design only; run RCA review and Action Gate; write `PLAN.md`; run plan-review iteration on `PLAN.md` until threshold + cold-read Go; then implement in slices.

For multiple plausible causes, use bounded investigation lanes only when they save context or real time. Do not start the next lane wave while a current lane has unresolved blockers, conflicting evidence, or a user decision.

If the existing fix status is `FIXED_UPSTREAM`, route to `/cherry-pick`. If it is `FIX_PENDING_PR`, stop and surface adopt/monitor/supersede choices.

## End-of-Workflow PROJECT.md Update (Hard Gate)

Before emitting the chat summary, append a `## Bug Fix Complete` entry to PROJECT.md so the durable record survives `/clear` or `/archive-project-file`. Required on every path — TRIVIAL/MODERATE single-shot runs included.

Minimum entry shape:

```markdown
## Bug Fix Complete
Bug: [one-line description or ticket]
Root cause: [one-liner]
Files changed: [list]
Regression test: [added / updated / accepted gap with reason]
Verification: [strength label]
Review Gate: [status]
QA: [pass / fail / skipped — reason] (if applicable)
Residual risk: [one-liner, or "none"]
Commit: [SHA or "no commit"]
```

For STANDARD runs that already wrote per-slice `## Slice N Complete` entries, this rollup summarizes the run; it does not replace those entries.

Emit before the chat summary:

```markdown
## PROJECT.md Updated — Bug Fix Complete
Entry recorded
```

Do not emit the chat summary until the `## PROJECT.md Updated — Bug Fix Complete` confirmation block has been emitted.
