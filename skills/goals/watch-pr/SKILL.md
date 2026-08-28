---
name: watch-pr
description: Use to watch, babysit, and monitor an open PR across CI and review comments over multiple iterations, routing fixes and replies, escalating on real blockers. Do NOT use for a one-off CI diagnosis (skills/goals/fix-ci), a single feedback round (skills/goals/address-feedback), or reviewing someone else's PR (skills/goals/code-review).
---

# Watch PR

## Before Starting

Read `rules/gates.md` (six-state gate contract), `rules/durable-workflows.md`,
and the `watch-pr` entry in `interfaces/contracts.json` (durable runtime:
effect `external_effect`, authorization mode `invocation` with gates
`publish-explicit`/`verification`/`pii-scrub`, phases prepare→poll→route→
checkpoint, resumable via `WATCH.md` + `PROJECT.md`) before continuing. This
skill is the v2 goal-skill entry point for PR babysitting; it delegates the
actual iteration/routing/stop procedure to `skills/pr-watch/SKILL.md` rather
than reimplementing it — read that skill in full before continuing, since
this skill's steps assume its Iteration/Routing/Stops/Recurrence shape.

## Scope

**In scope:** an open PR that needs unattended, multi-iteration babysitting —
checking CI, checking comments, routing fixes and replies, and escalating
when a delta can't be routed safely — until the watch reaches `stable`,
`escalated`, or `blocked`.

**Out of scope:** a single CI failure with no ongoing watch —
`skills/goals/fix-ci`, which this skill dispatches internally on every
CI-caused delta (see `skills/pr-watch/SKILL.md`'s Routing table), not a substitute for
this skill. A single round of review-comment triage/fix/reply — that is
`skills/goals/address-feedback`, likewise dispatched internally. Reviewing a
PR you didn't author — `skills/goals/code-review`.

## Steps

1. **Prepare.** Normalize the target: a PR number or URL. Check identity with
   `gh auth status` up front — replies posted during routing need this.
   Confirm the repository API is reachable per `skills/pr-watch/SKILL.md`'s Recurrence
   Reachability section before committing to an unattended
   `recurrence` binding; if it is not (VPN-restricted repo, no local
   scheduler available), report that the watch can only run interactively or
   from a VPN-connected host, and proceed on that basis rather than silently
   implying unattended coverage. Initialize `WATCH.md` from
   `skills/pr-watch/templates/watch-manifest.md` (Target, Config, initial
   `Status: watching`). Emit the visible Watch Started grant per
   `skills/pr-watch/SKILL.md`'s Authorization Boundary before the first effect.
2. **Iterate.** Follow `skills/pr-watch/SKILL.md`'s Iteration procedure in
   full — poll, classify, route (dispatching `skills/goals/fix-ci` or
   `skills/goals/address-feedback` wholesale per its Routing table; never
   reimplementing their diagnose/fix/verify/review logic here), checkpoint.
   Do not restate its dispatch or routing steps here; this skill delegates
   rather than reimplementing them.
3. **Stop.** Apply `skills/pr-watch/SKILL.md`'s Stops section exactly: an unresolved
   failure group surviving two fixes, a needed history rewrite/conflict, a
   required human decision, three flaky-class streak resets, unrelated dirty
   work, or twelve cumulative iterations without stability all end the watch
   with `Status: escalated`. A green-streak target reached with no comments
   past the cursor and no open escalation ends it with `Status: stable`.
4. **Report.** Record the terminal `WATCH.md` status and append a `##
   Watch Report` entry to `PROJECT.md` (iteration count, final status, what
   was dispatched and its outcomes, any escalation reason) before the run
   ends — this is the resumable checkpoint a fresh context or a `recurrence`
   reinvocation reads from, never chat memory.

## Output

The Watch Started grant, `WATCH.md`'s Iteration Log and Ledgers, and a
terminal status of `stable` (green target reached, no pending comments) or
`escalated`/`blocked` (with the specific stop reason and the state needed to
resume or hand off to a human).

## Notes

- Declares no dispatch boundaries of its own — CI-caused failures route
  through `skills/goals/fix-ci`'s own dispatch boundaries, and comment
  deltas through `skills/goals/address-feedback`'s; this skill only
  classifies and routes, it does not call a model route directly.
- `WATCH.md` is local-only, never committed — same rule as `PROJECT.md` /
  `PLAN.md`.
