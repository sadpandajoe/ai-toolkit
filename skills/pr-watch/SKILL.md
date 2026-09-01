---
name: pr-watch
description: Use for the iteration/routing/stop contract of babysitting an open PR — check CI, check comments, route deltas to existing fix skills, checkpoint. Internal support skill; `skills/goals/watch-pr` is the public entry point. Do NOT use directly for a one-off CI diagnosis or a single feedback round.
---

# PR Watch

## Before Starting

Read `rules/gates.md` (six-state gate contract), `rules/durable-workflows.md`,
and `rules/preset-environments.md`'s Network Reachability section (VPN
constraint on `recurrence` for Preset repos) before continuing. This skill
owns the iteration contract only — it does not reimplement fix logic. CI
failures route to `skills/goals/fix-ci` and comment deltas route to
`skills/goals/address-feedback`, both already six-state-gate-compliant and
already chaining `skills/verification-loop/SKILL.md`; this skill does not
duplicate their gates or add a second, private pass/fail mechanism.

## Iteration

One iteration is: check CI → check comments → route deltas → save `WATCH.md`
and the checkpoint. A fresh context must resume from those artifacts alone —
never from chat memory.

1. **Poll.** Run polling deterministically in the parent/tool layer (`gh pr
   checks`, `gh api .../comments` or equivalent). An `operations` worker may
   summarize only the already-collected read-only evidence; it does not
   execute API calls itself — the native `operations-worker` handles this
   summarization when `routed_subagent` is native for the provider,
   otherwise the plain `operations` route runs via `model-run` (no named
   Codex specialist contract). Return only changed run IDs, brief failure
   evidence, new comment/thread IDs, and a no-change marker.
2. **Classify.** Classify each delta on the main reasoning tier, against the
   Routing table below.
3. **Route.**
   - CI failure caused by the PR: dispatch `skills/goals/fix-ci` wholesale
     against the failing run — do not reimplement diagnose/implement/verify
     here. `fix-ci` returns its own six-state Gate outcome; treat `PASS` as
     resolved and reset the green streak, `BLOCKED`/`USER_DECISION` as this
     watch's escalation.
   - Comment/thread delta (bot or unambiguous human ask): dispatch
     `skills/goals/address-feedback` wholesale against the new comment scope
     — do not reimplement triage/fix/reply/resolve here.
   - Transient infrastructure failure: rerun only the failed run, at most
     twice per run ID, then classify as real and fall through to the CI-fix
     route above.
   - Pre-existing failure (predates this watch, unrelated to the PR's
     changes): record evidence in the Rerun Ledger; do not fix unrelated
     work.
   - Ambiguous, architectural, cross-cutting, or conflict work: escalate
     without guessing or posting — see Stops.
4. **Checkpoint.** When context thresholds fire, finish the iteration, update
   `WATCH.md` (template: `skills/pr-watch/templates/watch-manifest.md`), use
   `bin/aitk checkpoint`, and apply `context_reset` or its declared fallback.
5. A provider `recurrence` binding may reinvoke the workflow. It must resume
   from `WATCH.md` alone, increment the durable iteration count, and preserve
   the same authorization and stop rules — never re-derive scope from chat
   memory.

## Routing

| Delta | Action |
|-------|--------|
| Transient infrastructure failure | Rerun the failed run only, max 2× per run ID, then reclassify as real |
| CI failure caused by the PR | Dispatch `skills/goals/fix-ci`, verify, reset green streak |
| Pre-existing failure | Record evidence; do not fix unrelated work |
| Bot or unambiguous human comment | Dispatch `skills/goals/address-feedback` within authorized scope |
| Ambiguous / architectural / cross-cutting / conflict | Escalate without guessing or posting |

## Authorization Boundary

Invoking `watch-pr` grants standing authorization for fast-forward commits to
the PR branch (via the dispatched `fix-ci`/`address-feedback` runs) and
factual replies/resolution within the routed scope. It does not authorize
amend, rebase, force-push, other branches, merge, approval, requesting
changes, or expanded scope. Emit the visible Watch Started grant before the
first effect.

## Stops

Stop and persist `Status: escalated` when a failure group survives two fixes,
a history rewrite/conflict is needed, a human decision is required, three
distinct flaky resets occur, unrelated dirty work exists, or twelve
cumulative iterations complete without stability.

The watch is `stable` only when the green streak reaches its target, no
comments remain past the cursor, and no escalation remains. Default target is
one green; raise it to five after any flaky/transient failure unless the user
explicitly set another target.

## Recurrence Reachability

Before using `recurrence`, verify the execution environment can reach the
repository API. Per `rules/preset-environments.md`: cloud-backed bindings are
forbidden for VPN/IP-restricted repos (`superset-shell`, `superset-private`,
`manager`) — use a VPN-connected local fallback and report that it only runs
while the host and VPN are available. Public repos are unaffected. Provider
adapters own concrete scheduling syntax.
