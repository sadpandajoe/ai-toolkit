---
name: pr-watch
description: Babysitting an open PR — loop on CI status and incoming review comments, dispatch fixes through the debug and feedback skills, re-run transient infra failures, and escalate what needs human judgment. Do NOT use for one-off CI diagnosis (use debug/ via /fix-ci), a single feedback round (use feedback/ via /address-feedback), or reviewing someone else's PR (use review/).
user-invocable: false
---

# PR Watch

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella skill for the watch-and-fix loop. `/watch-pr` is the entry point. This skill owns the loop contract — iteration shape, dispatch, authorization boundary, escalation, and stop conditions. The fix engines are existing skills: `debug/` for CI failures, `feedback/` for comments. pr-watch routes to them; it never duplicates their procedures.

## The Iteration

One iteration = **check CI → check comments → dispatch → save state**. Every iteration must be resumable from `WATCH.md` alone (template: [templates/watch-manifest.md](templates/watch-manifest.md)). Chat history is the control surface, never the state store — a fresh session running `/start` → `/watch-pr` must be able to continue the watch from the manifest.

**Context policy** — the loop cannot clear its own context (`/clear` is a built-in only the user can run), so it survives long watches by never accumulating dispatch payloads in the first place:

1. **Check in a cheap subagent; spend only on deltas.** The poll is binary — something changed or it didn't — so it runs as a `model: haiku` check worker: execute the `gh` polling (including blocking on `gh run watch` while a run is in progress), diff against the WATCH.md cursor, streak, and recorded check-run states, and return a delta report — `no change`, or a factual list (failed run id + job names + brief error lines; new thread ids past the cursor). Raw check JSON and run-watch output stay in the worker. Judgment never runs on the check worker: failure classification (`ci-classify-failure.md`), comment routing, escalation evaluation, and the fix engines stay on the session model — one misclassified failure or misrouted comment costs more than the polling ever saves.
2. **Dispatch in subagents; the orchestrator stays thin.** Fix engines run as subagent workers with a compact handoff (same invariant as the cherry-pick batch flow). Diffs, CI logs, and review rounds stay in the worker; the orchestrator gets back only ledger-row-sized results — SHAs pushed, verification outcome, replies posted, residual risk — and writes them to WATCH.md. Dispatch workers inherit the session model — never downgrade a fix engine to the check tier.
3. **Clear points are user actions.** If the main thread still hits the reactive thresholds in `rules/context-management.md` (~70% context, cost), finish the in-flight iteration, run `/checkpoint`, and stop with: `Checkpoint saved. Run /clear, then /start to resume the watch.` One manual step; `/start` auto-resumes from the manifest. Prefer this clear-with-manifest stop over letting auto-compaction fire — compaction is lossy and silent, the manifest is exact. Like `/clear`, `/compact` is user-only: the loop can neither invoke compaction early nor prevent auto-compact near the limit. If auto-compact fires mid-watch anyway, treat the summary as untrusted and re-read WATCH.md before the next iteration — the manifest, not the summary, is the state.
4. **Headless layers reset for free — if they can reach the repo.** A `/schedule` routine starts every run in a fresh session that resumes from WATCH.md, so it is the cheapest layer for long watches on repos a cloud agent can read. It is **not usable for VPN-gated repos** — see Recurrence below. `/loop` re-invokes within the same conversation and does not reset context, which is exactly why points 1–2 matter there: a no-delta `/loop` iteration should add only a heartbeat line to the thread.

## Dispatch Table

| Event | Classify with | Action |
|-------|---------------|--------|
| CI run failed — transient infra pattern | `debug/references/ci-classify-failure.md` | `gh run rerun --failed` — no diagnosis, no fix attempt counted. Cap 2 reruns per run id (record in Rerun Ledger), then treat as real. |
| CI run failed — real, ours | `debug/references/ci-classify-failure.md` + `ci-fix-orchestration.md` | Run the `/fix-ci` fix path scoped to the failure group. Commit + push under the watch authorization. Reset the green streak. Count one fix attempt against the failure group. |
| CI run failed — pre-existing / not ours | `debug/references/ci-classify-failure.md` | Record evidence in the manifest; do not fix. If it blocks merge, escalate. |
| New bot comments (Copilot, etc.) | `feedback/references/gather-triage.md` | Full `/address-feedback` default handling: investigate, fix or rebut with evidence, reply, resolve thread. |
| New human comment — unambiguous, local ask | `feedback/references/gather-triage.md` | Auto-fix, verify, push; post a factual reply ("Done in `<sha>`") and resolve. Anything beyond a factual reply is judgment-shaped → escalate instead. |
| New human comment — ambiguous, architectural, or cross-cutting | — | Park in Escalations. Do not reply, do not guess. |
| Merge conflict with base | — | Escalate. Rebase is outside the watch authorization. |

All replies and commit messages pass the PII scrub from `feedback/references/reply-resolve.md` before posting.

Dispatches run as subagent workers with compact handoffs — see the Context policy above. The worker inherits the engine's own gates (classification, verification strength, Review Gate, PII scrub) and the watch's authorization boundary verbatim. The table's **Classify with** column always executes on the session model, using the check worker's delta report plus targeted re-reads as evidence — never inside the Haiku check worker.

## Authorization Boundary

Invoking `/watch-pr` grants standing authorization, for the duration of the watch, to:

- create **new commits** on the PR branch and push them (fast-forward only)
- post replies and resolve threads within the comment scope above

It does **not** authorize: amend, rebase, force-push, pushing any other branch, merging the PR, approving or requesting changes, or expanding fix scope beyond the failing surface / commented code. The `/watch-pr` invocation is the explicit, separate commit confirmation — the standing grant is the reason the command must emit the `## Watch Started` block declaring it before the first iteration.

## Escalation Rules (hard stops)

Stop watching and surface to the user when any of these fires:

- **2 failed fix attempts** on the same failure group
- the next git step would require **amend / rebase / force-push** or conflict resolution with base
- a human comment requires **judgment or architectural decision**
- the **green streak resets 3 times** from distinct flaky-class failures — the suite is unstable; more loop iterations won't fix it
- the local working tree is **dirty with unrelated work** at watch start
- **12 iterations** on this watch without reaching a stop condition — cumulative across context resets and scheduled re-runs; the counter lives in WATCH.md, not the session, so resets cannot launder a runaway loop

Escalation is a terminal state for the session: save the manifest with `Status: escalated`, list the open items, and report. Never push through a hard stop to keep the loop alive.

## Stop Conditions

The watch ends `stable` when **all** hold:

1. Green streak ≥ target (see below)
2. No unprocessed comments past the cursor
3. Escalations list is empty

**Adaptive green target**: default is **1** consecutive green. It rises to **5** (auto-rerun to confirm) when this watch fixed or observed any flakiness-class failure on this PR — flaky timing, flaky order-dependent, or transient infra — because a single green is weak evidence exactly there. `--greens N` forces a fixed target either way.

## Recurrence

Recurrence is layered on top, not built in:

- `/watch-pr <pr>` — in-session: iterate continuously until stable or escalated. While a run is in progress on the head SHA, block on `gh run watch` inside the check worker rather than polling from the orchestrator. A threshold stop + user `/clear` + `/start` resume is part of one logical watch, not an exit.
- `/loop /watch-pr <pr>` — long-horizon, self-paced re-invocation; right for comment babysitting after CI is stable. Runs locally, so it works on any repo the user's own `gh` can reach.
- A `/schedule` routine wrapping `/watch-pr <pr>` — headless cron babysitting. **Cloud-executed: only for repos whose GitHub API is reachable from the public internet.**

**Reachability gate — check before recommending `/schedule`.** `/schedule` routines run as cloud agents. If the PR's repo sits behind a corporate VPN or an IP allow-list (all Preset repos — `superset-shell`, `superset-private`, `manager`; see `rules/preset-environments.md`), the cloud agent cannot authenticate against the GitHub API and **every scheduled run fails to read PR state**. It does not degrade gracefully; it just never sees the PR. For those repos the watcher must run on a host that is on the VPN — in-session `/loop /watch-pr`, or a local `launchd` cron invoking headless Claude. Inherent limit of the local shapes: they only run while the machine is awake and VPN-connected.

In-session watches end at first CI-stable; suggest the loop layer (or `/schedule`, only if the reachability gate passes) for ongoing comment watch rather than idling in-session.
