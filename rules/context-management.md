# Context Management

At every **chain boundary** or **loop iteration**, apply proactive phase resets first, then check context depth and cost.

## Proactive Phase Reset Policy

When a phase has produced a durable artifact that the next phase can resume from, checkpoint and clear before continuing into the next expensive phase. Do this for STANDARD work by default, even when context depth and session cost are still low.

The goal is to make chat history disposable: files hold state, the next session resumes from those files, and the agent does not pay to replay investigation, planning, implementation, and review in one growing context.

Default by complexity:
- **TRIVIAL**: stay in one session unless a tool/log output is unexpectedly large.
- **MODERATE**: stay in one session by default; checkpoint/clear when logs, diffs, or review rounds become large, or before review if implementation context is noisy.
- **STANDARD / expensive**: checkpoint/clear at every major phase boundary once the current phase's durable artifact is updated.

STANDARD phase boundaries:
1. **Investigation/planning artifact written**: `PLAN.md`, `BUG_FIX.md`, `CI_FIX.md`, `CHERRY_PICK.md`, or equivalent manifest is current.
2. **Plan/RCA review accepted**: review scores, gate decision, and next implementation slice are written.
3. **Implementation slice or wave complete**: changed files, verification run, and next review target are written.
4. **Code review findings recorded**: `## Current Code Review` contains actionable findings, fix queue, pre-flight result, and next action.
5. **Code review fixes complete**: Review Gate status, remaining risks, and next validation/PR action are written.

For batch work, checkpoint/clear between waves by default. For non-trivial cherry-picks, checkpoint/clear after investigate/gate/plan and after apply/adapt/validate when a later push/report phase remains.

Skip the reset only when the next phase is tiny and the durable artifact is already enough to avoid loading prior raw context; record the skip reason in PROJECT.md if the workflow is STANDARD.

When the reset policy fires, run `/checkpoint --clear`. After `/clear`, run `/start` to reload PROJECT.md and resume from the artifact pointer.

### 1. Context depth (existing rule)
- **Below ~70%**: Continue automatically.
- **At or above ~70%**: Finish the current action, then checkpoint.

### 2. Session cost
Read session cost from the statusline JSON (`cost.total_cost_usd`) or estimate from conversation length. Thresholds:

- **Below $3** (green): Continue automatically.
- **$3–$8** (yellow): Be aware. Consider whether the remaining work justifies continuing in this session.
- **Above $8** (red): Finish the current action, then checkpoint. Don't ask — just do it.

Cost grows quadratically in long conversations (each API call replays the full history). A fresh session with a checkpoint is cheaper than continuing a bloated one, even with the reload overhead.

### Where to check
Chain boundaries: `/fix-bug` internal phase transitions, `/create-feature` planning → implementation, `/create-feature` implementation → review, etc.
Loop iterations: each `/create-feature` planning round, each `/review-code` round.
Sub-invocations: when `/create-feature`, `/fix-bug`, `/update-tests`, or `/fix-ci` calls `/review-code`.

**"Finish the current action"** means: complete the in-flight tool call, subagent, or review round. Don't cut off mid-edit or mid-test. But don't start the *next* phase — checkpoint first.

## Save & Continue Protocol

When a proactive phase reset fires, or either reactive trigger fires (context ≥ 70% OR cost > $8), run `/checkpoint`. It handles the full protocol:
1. Writes a continuation checkpoint to PROJECT.md (see `commands/checkpoint.md` for the canonical format)
2. Leaves uncommitted work untouched unless the calling workflow already has explicit commit authorization; otherwise records dirty state in PROJECT.md
3. Runs `/clear` to reset conversation context

After `/clear`, run `/start` to reload PROJECT.md and resume the saved workflow automatically.

The user's part is two commands — `/clear`, then `/start`; everything else restores from PROJECT.md. The model cannot run `/clear` itself, so `--clear` means "write state, then request the clear" — the workflow must end its turn on that request, not assume the clear happened.

Do not rely on chat memory after `/clear`. The checkpoint in PROJECT.md is the source of truth for where execution resumes.

## Native Session State Is Not Durable State

Session-scoped built-ins cannot hold workflow state across a reset, so they never replace the file-based record:

- **`/goal`** is removed by `/clear` and is user-only (an orchestrator cannot call it mid-workflow) — incompatible with the clear-and-resume discipline. Keep work going via command contracts and reactive thresholds, not `/goal`.
- **Native task tools** (`TaskCreate`/`TaskList`/`TaskUpdate`) survive `/clear` within one session but are lost on a fresh session, so the `## Slice N Complete`, Phase Plan, and fix-queue records that must outlive `/start` stay in PROJECT.md/PLAN.md. Native tasks may mirror the current phase as an **in-session working layer** — most useful on MODERATE single-session work that does not checkpoint/clear — but never as the durable copy.

The built-ins whose state lives *outside* the session are safe to lean on, and the toolkit already adopts them: `/schedule` routines (cloud-backed), `EnterWorktree` (git-backed), and the `Workflow` tool (stateless fan-out).

## Batch Manifest Checkpoints

For large batch workflows, checkpointing should preserve the manifest pointer and next unit/wave, not raw per-item history. The manifest is the source of truth; chat is only the control surface.

Examples:
- Cherry-pick trains: `PROJECT.md` points to `CHERRY_PICK.md`, current wave, and next PR/SHA.
- Multi-failure CI fixes: `PROJECT.md` points to `CI_FIX.md`, current failure group, and next verification step.
- Large feature builds: `PROJECT.md` points to `PLAN.md`, current slice/wave, and pending workstream handoffs.
- PR watches: `PROJECT.md` points to `WATCH.md`. Dispatches run in subagents to keep the orchestrator thin; clears happen at reactive thresholds (user runs `/clear`, `/start` resumes) and the iteration counter in the manifest survives them.

If a manifest exists, update it before `/checkpoint --clear` so resume does not depend on context that will be discarded.

## Reference Loading Policy

Commands should eagerly import only short rules the main thread needs immediately. Skills and detailed workflow references belong behind step routing: name or link the skill/reference in the command, then load it only when entering that step.

This preserves the old command reliability (the gates and sequence stay visible) without paying the token cost for every phase at command start. If a command needs a long procedure for only one branch of a workflow, keep it as a skill reference, not an `@{{TOOLKIT_DIR}}/...` import.

## Why This Matters
- **Context depth**: Auto-compaction silently drops earlier context, which can cause Claude to lose track of decisions, review scores, or chain state mid-workflow.
- **Session cost**: With a 1M context window, you can burn $50+ before hitting 70% context. Cost-based checkpointing catches the token burn that context % misses. A fresh session with a PROJECT.md checkpoint is both cheaper and higher fidelity than a long session with compacted history.
