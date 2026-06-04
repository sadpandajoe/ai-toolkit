# /fix-ci - Fix CI Failures

@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: A CI build has failed and you want the repo-standard workflow to diagnose it, apply safe fixes, verify locally, and stop before commit when risk remains.
> **Produces**: Failure classification, PROJECT.md update, safe fixes where appropriate, validation results, Review Gate status, and a recommended commit action.

## Usage
```
/fix-ci <run-url>          # Fix a specific CI run
/fix-ci <pr-number>        # Fix latest CI run for a PR
/fix-ci <log-file>         # Fix from a local CI log file
/fix-ci <zip-file>         # Fix from a local CI artifact bundle
/fix-ci                    # Fix latest failed CI run for current branch
```

## Command Contract

- Read actual failing log output before classifying.
- Keep raw logs out of chat when they are large; use log paths and compact excerpts.
- For 3+ failed jobs, artifact bundles, or large logs, create local `CI_FIX.md` via [skills/debug/templates/ci-fix-manifest.md](../skills/debug/templates/ci-fix-manifest.md).
- Group failures by root cause before fixing.
- Keep fixes scoped to the failing surface.
- Run local verification before review, and emit a Review Gate block whenever repo-tracked files changed.
- Update PROJECT.md at standard-path boundaries. Two updates are **hard gates with confirmation blocks** on every path: initial-triage entry before path branching (step 3 tail), Completed entry before the chat summary (step 9 head).
- The main thread owns `CI_FIX.md` and PROJECT.md. Subagents return compact handoffs; they do not update durable state directly.
- When verification is STRONG and the fix is approved, create a new commit on the current feature branch and push it as part of the fix flow. Pause for amend, rebase, or force-push, and when the push target is ambiguous (not the current feature branch, or tracks an unexpected remote). PARTIAL/WEAK verification and standard-path holds stay non-committing — present the diagnosis and stop.
- For STANDARD or expensive CI work, checkpoint/clear after `CI_FIX.md` or PROJECT.md captures classification/grouping, after Action Gate/RCA decisions, after local verification, and after `/review-code` when commit recommendation work remains.

## Happy Paths

- **Trivial**: gather logs, classify/group, apply the safe fix inline, verify locally, emit Review Gate `skipped`/`micro-fix` only when the Review Gate exception applies, update PROJECT.md when useful, summarize.
- **Moderate**: gather logs, classify/group, plan inline, apply inline by default, verify locally, run `/review-code`, update PROJECT.md, summarize.
- **Standard**: create/update `CI_FIX.md` when useful, checkpoint/clear, validate RCA when needed, run Action Gate, checkpoint/clear, apply only if the gate allows it, verify locally, review, then present commit recommendation.

## Steps

### 1. Normalize Input

Accept a GitHub Actions run URL, PR number, local log file, local zip artifact bundle, or no argument. With no argument, resolve the latest failed run for the current branch.

### 2. Gather Logs

Follow [skills/debug/references/ci-gather-logs.md](../skills/debug/references/ci-gather-logs.md).

Stop if no actual log output or artifact source can be resolved.
For Jenkins or authenticated external CI, stop after the first auth failure and ask for a log excerpt/artifact instead of reasoning from the dashboard.

### 3. Classify + Group Failures

Use [skills/debug/references/ci-classify-failure.md](../skills/debug/references/ci-classify-failure.md) for log classification.

Then load [skills/debug/references/ci-fix-orchestration.md](../skills/debug/references/ci-fix-orchestration.md) for grouping, ours/pre-existing classification, complexity routing, and commit recommendation strategy. Do not load the full orchestration reference before real logs exist.

If all failures are pre-existing or not caused by this branch, exit early with evidence and no fix/review cycle.

**Initial-triage PROJECT.md update (hard gate, all paths)**: Before branching to a path — including the not-our-failure exit — write the classification to PROJECT.md (failing run/source, classified failures, ours/pre-existing split, hypothesis per failure). Then emit:

```markdown
## PROJECT.md Updated — Initial Triage
Failures recorded: [count]
Path likely: [trivial/moderate/standard/not-our-failure]
```

This gate exists because a "this is mechanical, I already know what to do" mental frame forms at this exact moment and silently swallows every later PROJECT.md update. Writing the triage entry first breaks the frame. Do not proceed without emitting the block.

### 4. Complexity Gate

Emit the Complexity Gate block per `rules/complexity-gate.md`.

Route using the CI-specific matrix in [skills/debug/references/ci-fix-orchestration.md](../skills/debug/references/ci-fix-orchestration.md):
- **Trivial**: apply, verify, Review Gate skip/micro-fix only when allowed, update PROJECT.md when useful, summarize.
- **Moderate**: plan inline, apply, verify locally, then `/review-code`, update PROJECT.md, summarize.
- **Standard**: update PROJECT.md, validate RCA when needed, run Action Gate, then apply only if the gate allows it.

### 5. Apply Safe Fixes

Apply only the fix path selected by the grouped classification. For standard-path planning, use a bounded planning subagent only when it materially improves isolation or reasoning; the orchestrator applies the final patch.

### 6. Verify Locally

Follow [skills/debug/references/ci-verify-fix.md](../skills/debug/references/ci-verify-fix.md) and record verification strength as `STRONG`, `PARTIAL`, or `WEAK`.

### 7. Review Changed Files

If repo-tracked files changed, invoke `/review-code` on the changed files as an internal loop after local verification.

For zero-logic diffs, apply the skip rule from `rules/review-gate.md`. For true micro-fixes, apply the micro-fix rule only when relevant checks/tests pass. If any logic changed beyond micro-fix scope, do not skip `/review-code`.

### 8. Commit Recommendation

Use the commit recommendation strategy in [skills/debug/references/ci-fix-orchestration.md](../skills/debug/references/ci-fix-orchestration.md).

Do not commit standard-path or PARTIAL/WEAK fixes automatically. For STRONG-verified trivial/moderate fixes with a clean Review Gate, create a new commit on the current feature branch and push it. Pause for amend, rebase, or force-push, and when the push target is ambiguous. For PARTIAL/WEAK or standard-path holds, present the diagnosis, verification gap, and recommended next action without committing.

### 9. Summary + Metrics

**PROJECT.md Completed Entry first (hard gate, all paths)**: Before emitting the chat summary, append a `Completed` entry to PROJECT.md (date, one-line scope, commit SHA(s) if any, verification strength) and remove any now-resolved "Not done" / "Pending" bullets that this run closed out. Chat summary and PROJECT.md Completed entry serve **different audiences** — chat is in-session, PROJECT.md is the cross-session handoff that `/start` reloads. Letting the chat summary stand in for the PROJECT.md entry is the single most common way this discipline is silently dropped.

Do not emit the chat summary template below until this confirmation block is emitted:

```markdown
## PROJECT.md Updated — Completed Entry
Entry appended: [one-line scope]
Resolved bullets removed: [count, or "none"]
```

Then use the summary shapes in [skills/debug/references/ci-fix-orchestration.md](../skills/debug/references/ci-fix-orchestration.md).

Record metrics with:
- `command`: `fix-ci`
- `complexity`: `trivial` / `moderate` / `standard`
- `status`: Review Gate status
- `rounds`: total review iteration rounds
- `gate_decisions`: complexity, action gate, review, verification strength
- `worker_usage`: subagent/worker invocation counts when applicable

## PROJECT.md Update Discipline

Two updates are **hard gates** with confirmation blocks (every path):
- Initial triage — emitted at the end of step 3, before path branching
- Completed entry — emitted at the start of step 9, before the chat summary

On the **standard path**, also update PROJECT.md compactly at these mid-flow points (no confirmation block required, but expected):
- after RCA validation when it runs
- after the Action Gate
- after local verification and `/review-code`

Keep updates compact. If `CI_FIX.md` exists, PROJECT.md should point to it rather than duplicating its table. The chat summary at step 9 does **not** substitute for the PROJECT.md Completed entry — they serve different audiences (in-session vs. cross-session).
