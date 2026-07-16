# /create-feature - End-to-End Feature Workflow

@{{TOOLKIT_DIR}}/rules/input-detection.md
@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: You have a feature request or planned non-bug work and want the repo-standard workflow to scope, review, implement, and validate it.
> **Produces**: Feature brief when needed, implementation plan, reviewed plan, local changes, Review Gate, QA results when relevant, and a handoff before final PR action.

## Usage

```bash
/create-feature "add bulk edit for dashboard filters"
/create-feature sc-12345
/create-feature apache/superset#28456
/create-feature https://github.com/owner/repo/issues/123
/create-feature https://app.shortcut.com/.../story/123
/create-feature sc-12345 --watch   # once a PR exists and the final push lands, chain into /watch-pr
```

## Command Contract

The command owns the visible gates and sequence. Each step loads only the referenced skill phase when that step starts; do not eagerly load skill indexes or phase references up front.

- Emit a Complexity Gate before planning or implementation.
- Fetch ticket context before classification or implementation when the input is a ticket or issue.
- For STANDARD work, write `PLAN.md` and update PROJECT.md before review iterations.
- Do not implement STANDARD work until the `PLAN.md Written` block is emitted.
- Run `/verify` or equivalent pre-flight checks before `/review-code`, and record the result in the Review Gate. Run `/review-code` after each meaningful implementation slice or wave.
- For TRIVIAL work, use the Review Gate exception only for zero-logic diffs or true micro-fixes. If a TRIVIAL change needs logic review beyond those exceptions, reclassify as MODERATE and run `/review-code`.
- Stop before final commit/PR for MODERATE or STANDARD work unless the user already authorized that boundary.
- With `--watch`, after a PR exists and the final push lands, chain into `/watch-pr` on that PR — the flag is the explicit pre-authorization for the watch's standing commit+push grant. Without the flag, end with a one-line `/watch-pr` suggestion when an open PR exists; never enter the watch unflagged.
- Only the main thread writes PROJECT.md or `PLAN.md`. Subagents return handoffs; the orchestrator updates durable state.
- For STANDARD work, follow `rules/context-management.md`: checkpoint/clear after `PLAN.md` is written, after plan review/action gate accepts, after each implementation slice or wave, and after code review fixes when validation/PR work remains.
- For STANDARD work, emit the Phase Plan block from `rules/complexity-gate.md` immediately after the Complexity Gate.
- **`## Slice N Complete` PROJECT.md write is a hard gate** before every per-slice checkpoint/clear on the STANDARD path. No clear without the entry.
- **`## Feature Complete` PROJECT.md write is a hard gate** before the chat summary on every path. TRIVIAL/MODERATE single-shot runs need this so `/clear` or `/archive-project-file` after `/create-feature` does not lose the result. STANDARD runs that ended with a per-slice entry must still emit the rollup before the summary. See the end-of-workflow section below.

## Planning Phase Boundary

The planning phase is a workflow boundary. For STANDARD work, automatically start it after the Complexity Gate. Use the platform's native planning/read-only mode when available — `EnterPlanMode` to enter, `ExitPlanMode` to leave; otherwise announce the planning phase and self-enforce the same boundary.

During the planning phase, read, search, fetch ticket context, inspect code, and draft the approach. Do not make implementation edits of any kind, change tests, run implementation workers, or start review iterations. If native planning/read-only mode cannot write files, exit that mode (`ExitPlanMode`) after drafting, then write `PLAN.md` as the planning-phase output. End the phase by updating PROJECT.md with the active-plan pointer and emitting `PLAN.md Written`:

```markdown
## PLAN.md Written
Plan: PLAN.md
Project state: PROJECT.md updated
Next: [first implementation slice or user decision]
```

TRIVIAL and MODERATE work skip the formal planning phase. For MODERATE work, load a targeted planning reference only when a specific ambiguity needs it; if durable plan review or slice orchestration becomes necessary, reclassify as STANDARD.

## Feature Complexity Signals

Use these command-specific signals with `rules/complexity-gate.md`:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Files touched | 1-2 | 2-4, clear single subsystem | 3+ across subsystems, unclear scope, or cross-cutting ownership |
| Design decisions | None | Known pattern | Real trade-offs |
| New APIs or migrations | No | Minor extension | Yes or cross-system |
| Behavioral risk | Mechanical/cosmetic | Contained functional change | Cross-cutting functional change |

MODERATE is the default for real but contained feature work. Use STANDARD when the feature needs durable planning, plan-review iteration, multiple review/fix waves, or slice/workstream orchestration.

There is no `COMPLEX` classification. Larger efforts stay STANDARD with explicit modifiers such as workstreams, migration, security-sensitive, or unclear scope.

## TRIVIAL Happy Path

1. Normalize the request, fetch ticket context if present, and emit the Complexity Gate.
2. Implement inline.
3. Run the smallest meaningful verification.
4. Emit a Review Gate `skipped` block for a zero-logic diff, or `micro-fix` only when the micro-fix rule passes. Reclassify as MODERATE if the change needs logic review beyond those exceptions.
5. Summarize; commit/push only with STRONG verification per the [verification strength labels](verify.md) and prior authorization.

## STANDARD Happy Path

1. Normalize the request and fetch ticket context if present.
2. Emit the Complexity Gate with the feature signals above.
3. Load PM scoping only if scope, milestones, acceptance criteria, or rollout are non-trivial.
4. Load technical planning, produce slices, write `PLAN.md`, update PROJECT.md, and emit `PLAN.md Written`.
5. Checkpoint/clear, then resume from `PLAN.md` and PROJECT.md before plan review.
6. Load the plan-review loop; fresh reviewer subagents return findings and scores; the main thread updates the plan until material findings are resolved and the Action Gate says proceed.
7. Checkpoint/clear, then implement one bounded slice or wave inline by default, or with one bounded implementation subagent when isolation or parallelism clearly helps; any subagent returns `Implementation Handoff` blocks only.
8. Main thread updates `PLAN.md`/PROJECT.md, runs fan-in if needed, then runs `/verify` or equivalent pre-flight checks. **Hard gate before the next checkpoint/clear**: append a `## Slice N Complete` block to PROJECT.md (slice name, files changed, tests added/updated, acceptance result, next slice or "ready for review"). Do not invoke `/checkpoint --clear` until this block is written:

   ```markdown
   ## Slice N Complete
   Slice: [name]
   Files changed: [list]
   Tests: [added/updated/none]
   Acceptance: [passed/failed/not runnable — reason]
   Next: [next slice name OR "ready for /review-code"]
   ```

9. Checkpoint/clear before `/review-code` when implementation context is non-trivial, then invoke `/review-code` from the changed-file list, plan pointer, and pre-flight result.
10. After code review fixes are done, checkpoint/clear before feature validation or PR work if the review loop was non-trivial.
11. Run feature validation when user-visible behavior changed.
12. Load the summary template and stop before final commit/PR unless authorized.

## MODERATE Happy Path

1. Normalize the request, fetch ticket context if present, and emit the Complexity Gate.
2. Resolve enough scope inline to avoid guessing; write compact PROJECT.md action items if the work may span turns.
3. Load PM or technical planning references only if a specific ambiguity needs them.
4. Implement inline by default, or hand off to one bounded implementation subagent if isolation clearly helps. Non-isolated implementation handoffs never include commits.
5. Run `/verify` or equivalent pre-flight checks, then one fresh review pass through `/review-code`.
6. Validate user-visible behavior if applicable, then summarize.

## Step Routing And Handoffs

Use the happy paths and path rules as the primary flow. Use this table as a phase lookup when entering a step; do not preload every linked route.

| Step | Owner | Route | Load / hand off when |
|------|-------|-------|----------------------|
| Normalize input | Main thread | `rules/input-detection.md` | Load immediately. Fetch ticket context before classification or implementation. |
| Complexity Gate | Main thread | `rules/complexity-gate.md` | Load immediately. Choose TRIVIAL, MODERATE, or STANDARD path. |
| PM scoping | Main thread by default; PM subagent only for broad scope | [skills/pm/references/create-feature-brief.md](../skills/pm/references/create-feature-brief.md), [plan-milestones.md](../skills/pm/references/plan-milestones.md) | Load only when scope, milestones, acceptance criteria, or rollout are non-trivial. Broad means multiple product surfaces, rollout or permissions decisions, or unclear acceptance criteria. Handoff: product constraints and acceptance criteria. |
| Technical plan | Main thread by default; planning subagent only for broad STANDARD design | [skills/planning/references/plan-implementation.md](../skills/planning/references/plan-implementation.md) | Load on STANDARD path, or MODERATE path with design uncertainty. Output must include slices, dependencies, entrance/exit criteria, and acceptance checks. |
| PLAN.md gate | Main thread | PROJECT.md + `PLAN.md` | STANDARD path only. Write the plan and emit `PLAN.md Written` before implementation. |
| Plan review | Fresh reviewer subagents via planning loop | [skills/planning/references/iterate-review.md](../skills/planning/references/iterate-review.md), [finalize.md](../skills/planning/references/finalize.md), `action-gate` | Load after `PLAN.md` is written. Use fresh reviewers for each review pass after material plan revisions; reuse a reviewer only for clarifying that reviewer's own finding in the same pass. Continue after material findings are resolved and the Action Gate says proceed; otherwise stop on blocker or user decision. |
| Implementation | Main thread for trivial/tightly-coupled work; `implement-change/` subagent for bounded slices | [skills/implement-change/SKILL.md](../skills/implement-change/SKILL.md) | Start after inline design/action items for MODERATE, or after `PLAN.md Written` for STANDARD. Implement inline by default; delegate one bounded slice only when isolation or parallelism helps. Prompt includes only slice name, scope/files, entrance criteria, exit criteria, acceptance checks, relevant plan excerpt, branch/base, and whether `isolation: "worktree"` is enabled. Non-isolated subagents must not commit. Return `Implementation Handoff`. |
| Workstream fan-in | Main thread | [skills/workstreams/references/sync.md](../skills/workstreams/references/sync.md) | Load after parallel slice handoffs complete. Use isolated worktrees only when slices can commit independently with disjoint ownership; each handoff includes branch/commit identity. Merge/sync only when all slice handoffs pass their exit criteria. Subagents do not update PROJECT.md directly. |
| Review | `/review-code` reviewer subagents | [skills/review/references/local-review.md](../skills/review/references/local-review.md) | Run after `/verify` or equivalent pre-flight checks for each meaningful implementation slice or wave. Branch on the Review Gate status before starting another wave. |
| Feature validation | Main thread by default; QA subagent only for large independent scenario sets | [skills/qa/references/validate-feature.md](../skills/qa/references/validate-feature.md) | Load when user-visible behavior changed and app is runnable. Return pass/fail/blockers and evidence paths. |
| Summary | Main thread | [skills/reporting/templates/create-feature-summary.md](../skills/reporting/templates/create-feature-summary.md), `metrics-emit` when available for the workflow | Load at workflow end or stop point. State verification strength, review status, feature-validation result, and why validation was skipped if the app was not runnable. |

## Path Rules

- **Trivial**: skip the formal planning phase and subagents; implement and test inline. Zero-logic diffs emit Review Gate `skipped`; true micro-fixes emit `micro-fix` only when the micro-fix rule passes. If logic review is needed beyond those exceptions, reclassify as MODERATE. Commit/push only with STRONG verification per the [verification strength labels](verify.md) and clean review; stop before PR creation.
- **Moderate**: design inline, write PROJECT.md action items when useful, implement inline by default, then run `/verify` or equivalent pre-flight checks and one fresh `/review-code` pass after implementation. Run plan review only if inline design uncovered real design uncertainty. Hand off to one bounded implementation subagent only when isolation or parallelism clearly helps; non-isolated implementation handoffs never include commits.
- **Standard**: use the planning phase for exploration/design only; write `PLAN.md`; run plan review and action gate; then implement in slices.

For 3+ independent slices, treat the work as STANDARD with workstreams and keep the main thread as a thin orchestrator. `PLAN.md` owns the slice table, dependencies, entrance/exit criteria, and acceptance checks. PROJECT.md records only the active slice/wave and next action. Load `rules/orchestration.md` only when deciding subagent batch size, workstream fan-in, or reasoning effort.

## End-of-Workflow PROJECT.md Update (Hard Gate)

Before emitting the chat summary, append a `## Feature Complete` entry to PROJECT.md so the durable record survives `/clear` or `/archive-project-file`. Required on every path — TRIVIAL/MODERATE single-shot runs included.

Minimum entry shape:

```markdown
## Feature Complete
Feature: [one-line description or ticket]
Slices delivered: [count, or "single-shot"]
Files changed: [summary or count]
Tests added/updated: [list or count]
Verification: [strength label]
Review Gate: [status]
Feature validation: [pass / fail / skipped — reason] (if applicable)
Residual risk: [one-liner, or "none"]
PR: [URL or "no PR yet"]
```

For STANDARD runs that already wrote per-slice `## Slice N Complete` entries, this rollup summarizes the run; it does not replace those entries.

Emit before the chat summary:

```markdown
## PROJECT.md Updated — Feature Complete
Entry recorded
```

Do not emit the chat summary until the `## PROJECT.md Updated — Feature Complete` confirmation block has been emitted.
