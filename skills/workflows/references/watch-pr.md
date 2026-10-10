# Watch a PR and Fix What Arrives

> **When**: A PR is open and you want an unattended loop that monitors CI and review comments, fixes what is safely fixable, and escalates the rest.
> **Produces**: A `WATCH.md` manifest, fixes pushed under standing authorization, replies/resolutions on eligible threads, and a terminal status of `stable`, `escalated`, or `blocked`.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `watch-pr` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```bash
watch-pr                     # Watch the PR for the current branch
watch-pr <pr-number-or-url>  # Watch a specific PR
watch-pr <pr> --greens N     # Force a fixed consecutive-green target
watch-pr <pr> --no-comments  # CI only; leave comments untouched
watch-pr <pr> --gate-strict  # WEAK verification is BLOCKED even when CI verifies downstream
```

Fix dispatches push only on `STRONG` verification (`rules/gates.md`,
Verification Strength); a `PASS (downstream: CI)` result is recorded and the
next iteration reads CI as the verifier.

Recurrence layers on top through the current provider binding. Load that binding
before choosing the mode: a remote/headless recurrence cannot reach VPN-gated
repositories, while a declared local/manual reinvocation fallback can. Apply the
reachability gate in [skills/pr-watch/SKILL.md](../../pr-watch/SKILL.md#recurrence-reachability)
to the selected execution environment, not to the generic capability name.
In-session, `watch-pr` iterates until stable or escalated, then suggests an
available recurrence layer if comment watching should continue.

## Authorization Boundary

Authorization mode: `invocation`. The invocation grants only the standing
current-PR commit, fast-forward push, and eligible reply/resolution scope stated
below; history rewriting, merge, review decisions, and other branches are not
authorized.

## Command Contract

The loop contract — iteration shape, dispatch table, authorization boundary, escalation rules, stop conditions — lives in [skills/pr-watch/SKILL.md](../../pr-watch/SKILL.md). The fix engines are the existing `fix-ci` path (via [skills/debug/](../../debug/SKILL.md)) and the `address-feedback` path (via [skills/feedback/](../../feedback/SKILL.md); its default is unattended for bot/posting work). This command never duplicates their procedures.

- **Standing authorization**: invoking `watch-pr` authorizes new commits + fast-forward pushes to the PR branch and replies/resolution within the comment scope, for the duration of the watch. It does not authorize amend, rebase, force-push, merge, approve/request-changes, or pushing any other branch. The invocation is the commit confirmation; the `## Watch Started` block makes the grant explicit.
- **Comment scope**: bot threads get full auto handling (fix, rebut with evidence, reply, resolve). Human comments are auto-fixed only when the ask is unambiguous and local; replies to humans stay factual ("Done in `<sha>`"). Everything judgment-shaped is escalated, never guessed.
- **State lives in WATCH.md**, created from [skills/pr-watch/templates/watch-manifest.md](../../pr-watch/templates/watch-manifest.md). PROJECT.md points to it; chat is never the state store. Resolve symlinks before writing (`readlink -f`).
- Every fix dispatch inherits its engine's own gates (classification, verification strength, review gate, PII scrub). The watch adds no shortcuts around them.
- **Context control is subagent isolation.** Fix dispatches use `implementation` and return compact handoffs; classification and diagnosis stay on the main thread or use `rca`/`deep-rca`. Check JSON, CI logs, diffs, and review rounds stay out of the orchestrator thread, so an idle iteration costs only a heartbeat. WATCH.md and the checkpoint are current after every iteration, so a session that ends for any reason resumes from them through the start workflow. For resets across sessions, use the selected provider recurrence binding only when its execution environment can reach the repository; otherwise use its declared local/manual fallback.
- **The watch runs unattended.** Between stop conditions, keep iterating instead of ending the turn with a plan, a status update, or a question; the only pauses are the skill's stop conditions and the authorization limits above.

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

Record the watch in PROJECT.md (top-level workflow `watch-pr <pr>`, pointer to WATCH.md) so `start` can resume it.

### 2. Iterate

Run iterations per the skill's dispatch table until a stop condition or hard stop fires:

<!-- aitk-model-route:workflows.watch-pr-poll -->
1. **Check (parent tools + operations summary)**: read the head SHA's merged check rollup (`gh pr view <pr> --json headRefOid,statusCheckRollup`, which includes the external `StatusContext` checks that `gh run watch` never shows; `rules/ci-evidence.md`) and, unless `--no-comments`, comment threads newer than the cursor. Between checks, wait with a background or scheduled wait when the harness offers one, otherwise a bounded blocking poll. Compare the result with the WATCH.md cursor in the parent; spawn an `operations` worker only to reduce a large failure log to run id, job, and error lines. **No delta → skip to step 3**.
<!-- aitk-model-route:workflows.watch-pr-fix -->
2. **Act on deltas (session model)**: CI failure → classify (`debug/references/ci-classify-failure.md`). Transient → rerun the failed GitHub Actions jobs yourself (`gh run rerun <run-id> --failed`, cap 2 per run id); reruns apply only to Actions runs. A failed external `StatusContext` (Jenkins and the like) cannot be rerun from here: it goes to classification like any other failure, and a transient one is reported and waited on, or escalated. Real and ours → dispatch the `fix-ci` fix path to an `implementation` worker, push, reset the streak. Pre-existing → record, escalate only if merge-blocking. New comments → route per the skill's Routing section through the feedback skill references. Classification and routing never run on the check worker.
3. **Evaluate stop conditions** from the skill: green streak ≥ target AND no unprocessed comments AND empty escalations → `stable`. An iteration is green only when every rollup entry for the head SHA, Actions and external, has passed; while any one is failing or pending the watch never reports `stable`. Any hard stop → `escalated`.
4. **Save state**: update WATCH.md `## State` and the checkpoint before the next iteration starts, because a fresh session resumes from them alone. When the iteration changed something (a fix, a rerun, a reply, an escalation), tell the user briefly what changed and the current streak; an idle iteration needs no message.

If the session must end mid-watch (checkpoint, user interrupt), WATCH.md keeps `Status: watching` and the PROJECT.md checkpoint names the resume target.

### 3. Terminal

On `stable`, `escalated`, or `blocked`, append a `## Watch Result` entry to PROJECT.md before the chat summary, so a fresh session sees the outcome without reopening WATCH.md:

```markdown
## Watch Result
PR #[number]: [stable / escalated / blocked] (manifest: WATCH.md)
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

If CI is stable but the PR stays open for human review, suggest the selected
`recurrence` binding for ongoing comment watch. Remote bindings require the
repository reachability gate; local/manual fallbacks remain eligible for
VPN-gated repositories.

**Record metrics**: `bin/aitk metrics emit --workflow watch-pr --status
<terminal status> --extra rounds=<iterations> --extra 'decisions={"ci_fixes":
N, "transient_reruns": N, "comments_fixed": N, "comments_rebutted": N,
"comments_escalated": N, "green_target": N}' [--workers <route>=<n> …]`;
add `--extra complexity=<trivial | standard | complex>` (`trivial` when the
watch dispatched no fix).
