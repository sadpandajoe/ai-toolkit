# /watch-pr - Watch a PR and Fix What Arrives

> **When**: A PR is open and you want an unattended loop that monitors CI and review comments, fixes what is safely fixable, and escalates the rest.
> **Produces**: A `WATCH.md` manifest, fixes pushed under standing authorization, replies/resolutions on eligible threads, and a terminal status of `stable`, `escalated`, or `blocked`.

## Usage

```bash
/watch-pr                     # Watch the PR for the current branch
/watch-pr <pr-number-or-url>  # Watch a specific PR
/watch-pr <pr> --greens N     # Force a fixed consecutive-green target
/watch-pr <pr> --no-comments  # CI only; leave comments untouched
```

Recurrence layers on top: `/loop /watch-pr <pr>` for self-paced long-horizon babysitting, or a `/schedule` routine for headless cron runs. In-session, `/watch-pr` iterates until stable or escalated, then suggests the loop/schedule layer if comment watching should continue.

## Command Contract

The loop contract — iteration shape, dispatch table, authorization boundary, escalation rules, stop conditions — lives in [skills/pr-watch/SKILL.md](../skills/pr-watch/SKILL.md). The fix engines are the existing `/fix-ci` path (via `skills/debug/`) and the `/address-feedback` path (via `skills/feedback/`; its default is unattended for bot/posting work). This command never duplicates their procedures.

- **Standing authorization**: invoking `/watch-pr` authorizes new commits + fast-forward pushes to the PR branch and replies/resolution within the comment scope, for the duration of the watch. It does not authorize amend, rebase, force-push, merge, approve/request-changes, or pushing any other branch. The invocation is the commit confirmation; the `## Watch Started` block makes the grant explicit.
- **Comment scope**: bot threads get full auto handling (fix, rebut with evidence, reply, resolve). Human comments are auto-fixed only when the ask is unambiguous and local; replies to humans stay factual ("Done in `<sha>`"). Everything judgment-shaped is escalated, never guessed.
- **State lives in WATCH.md**, created from [skills/pr-watch/templates/watch-manifest.md](../skills/pr-watch/templates/watch-manifest.md). PROJECT.md points to it; chat is never the state store. Resolve symlinks before writing (`readlink -f`).
- Every fix dispatch inherits its engine's own gates (classification, verification strength, Review Gate, PII scrub). The watch adds no shortcuts around them.
- **Context control is subagent isolation, not self-clearing** — the loop cannot run `/clear` (built-ins are user-only). The CI/comment poll runs as a `model: haiku` check worker returning a binary delta report, and fix dispatches run as subagent workers returning compact handoffs — so check JSON, run-watch output, diffs, CI logs, and review rounds never enter the orchestrator thread, and an idle iteration costs a heartbeat. The session model spends only when the check worker reports a delta. If the main thread still hits the reactive thresholds (~70% context, cost), it checkpoints and stops with `Checkpoint saved. Run /clear, then /start to resume the watch.` — one manual step, then `/start` auto-resumes from WATCH.md. For zero-touch resets, run the watch under a `/schedule` routine: every scheduled run is a fresh session resuming from the manifest.

## Steps

### 1. Preflight

- Resolve the PR: argument, or `gh pr view` for the current branch. No open PR → exit `blocked`.
- Verify `gh` auth and that the local checkout matches the PR head branch (fetch if behind; **dirty working tree with unrelated changes → escalate immediately**, do not stash).
- Find or create `WATCH.md` from the template.

Then emit the authorization declaration (hard gate — no iteration before this block):

```markdown
## Watch Started
PR: #[number] — [title]
Branch: [head] ← [base]
Green target: [N] (adaptive | forced)
Comment scope: [bots + clear human asks | CI only]
Standing auth: new commits + ff push to [head]; no amend/rebase/force-push/merge/approve
```

Record the watch in PROJECT.md (top-level command `/watch-pr <pr>`, pointer to WATCH.md) so `/start` can resume it.

### 2. Iterate

Run iterations per the skill's dispatch table until a stop condition or hard stop fires:

1. **Check (Haiku worker)**: spawn a `model: haiku` subagent to poll the head SHA — check-run states (blocking on `gh run watch` while a run is in progress, re-invoking past tool timeouts) and, unless `--no-comments`, comment threads newer than the cursor. The worker diffs against WATCH.md and returns a delta report: `no change`, or a factual list (failed run id + job names + brief error lines; new thread ids). Raw check JSON and run-watch output stay in the worker. **No delta → skip to step 3** — nothing else spends.
2. **Act on deltas (session model)**: CI failure → classify (`debug/references/ci-classify-failure.md`), then dispatch: transient → rerun (cap 2/run id); real+ours → `/fix-ci` fix path, push, reset streak; pre-existing → record, escalate only if merge-blocking. New comments → route per the dispatch table through the feedback skill references. Classification and routing never run on the check worker.
3. **Evaluate stop conditions** from the skill: green streak ≥ target AND no unprocessed comments AND empty escalations → `stable`. Any hard stop → `escalated`.
4. **Save state** (hard gate — no iteration ends without it):

```markdown
## Watch State Saved — Iteration [N]
Streak: [n]/[target] | Fixes: [n] | Reruns: [n] | Comments handled: [n] | Escalations: [n]
```

5. **Context check**: if a reactive threshold fired (~70% context or cost), run `/checkpoint` — it names `/watch-pr <pr>` as the top-level command and WATCH.md as the manifest (extension: `skills/reporting/templates/watch-pr-checkpoint.md`) — then stop with `Checkpoint saved. Run /clear, then /start to resume the watch.` Otherwise continue to the next iteration; dispatch payloads stayed in their workers, so the orchestrator thread grows slowly.

If the session must end mid-watch (checkpoint/clear, user interrupt), WATCH.md keeps `Status: watching` and the PROJECT.md checkpoint names the resume target.

### 3. Terminal

On `stable`, `escalated`, or `blocked`, append to PROJECT.md before the chat summary (hard gate):

```markdown
## PROJECT.md Updated — Watch Complete
PR #[number]: [stable / escalated / blocked]
```

Then summarize:

```markdown
## Watch Complete
PR #[number] — [stable / escalated / blocked] after [N] iterations

### CI
- Fixes pushed: [list with SHAs, or "none"]
- Transient reruns: [N]
- Final streak: [n]/[target]

### Comments
- Fixed: [N] | Rebutted: [N] | Escalated: [N]

### Escalations (need you)
- [item + why the loop stopped, or "none"]
```

If CI is stable but the PR stays open for human review, suggest `/loop /watch-pr <pr>` or a `/schedule` routine for ongoing comment watch.

**Record metrics**:
- `command`: `watch-pr`
- `complexity`: `moderate` (or `standard` when a dispatched fix was standard-path)
- `status`: terminal status
- `rounds`: iteration count
- `gate_decisions`: `{ ci_fixes: <N>, transient_reruns: <N>, comments_fixed: <N>, comments_rebutted: <N>, comments_escalated: <N>, green_target: <N> }`
- `worker_usage`: subagent/worker invocation counts when applicable
