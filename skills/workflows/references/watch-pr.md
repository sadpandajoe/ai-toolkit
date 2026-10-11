# Watch a PR and Fix What Arrives

> **When**: A PR is open and you want an unattended loop that monitors CI and review comments, fixes what is safely fixable, and escalates the rest.
> **Produces**: A `WATCH.md` manifest, fixes pushed under standing authorization, replies/resolutions on eligible threads, and a terminal status of `stable`, `escalated`, or `blocked`.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

`watch-pr` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`.

## Usage

```bash
watch-pr                     # Watch the PR for the current branch
watch-pr <pr-number-or-url>  # Watch a specific PR
watch-pr <pr> --greens N     # Force a fixed consecutive-green target
watch-pr <pr> --no-comments  # CI only; leave comments untouched
watch-pr <pr> --gate-strict  # WEAK verification is BLOCKED even when CI verifies downstream
```

## Authorization Boundary

Authorization mode: `invocation`. Authorization, the iteration contract,
stops, and recurrence live in [skills/pr-watch/SKILL.md](../../pr-watch/SKILL.md).
The fix engines are the `fix-ci` path ([skills/debug/](../../debug/SKILL.md))
and the `address-feedback` path ([skills/feedback/](../../feedback/SKILL.md));
this workflow never duplicates their procedures.

## Steps

### 1. Preflight

- Resolve the PR: argument, or `gh pr view` for the current branch. No open PR → exit `blocked`.
- Verify `gh` auth and that the local checkout matches the PR head branch (fetch if behind; **dirty working tree with unrelated changes → escalate immediately**, do not stash).
- Find or create `WATCH.md` from [skills/pr-watch/templates/watch-manifest.md](../../pr-watch/templates/watch-manifest.md). It is the state store and PROJECT.md points to it; write to its `readlink -f` target.

Then emit the authorization declaration (hard gate — no iteration before this
block; on resume, emit it again before the first effect):

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

Run iterations per the skill's Iteration, Routing, and Stops sections until a
stop fires.
<!-- aitk-model-route:workflows.watch-pr-fix -->
For a real failure the PR caused, dispatch the `fix-ci` fix path to an `implementation` worker; it returns a compact handoff, and the parent pushes and resets the streak. Classification and routing stay with the session model.

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

If CI is stable but the PR stays open for human review, suggest a
`recurrence` binding for ongoing comment watch that the skill's Recurrence
Reachability allows.

**Record metrics**: `bin/aitk metrics emit --workflow watch-pr --status
<terminal status> --extra rounds=<iterations> --extra 'decisions={"ci_fixes":
N, "transient_reruns": N, "comments_fixed": N, "comments_rebutted": N,
"comments_escalated": N, "green_target": N}' [--workers <route>=<n> …]`;
add `--extra complexity=<trivial | standard | complex>` (`trivial` when the
watch dispatched no fix).
