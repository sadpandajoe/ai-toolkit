---
name: pr-watch
description: Babysit an open PR by monitoring CI and review comments, routing bounded fixes, and escalating decisions. Use for a durable watch-pr run. Do NOT use for one-off CI diagnosis, a single feedback round, or reviewing someone else's PR.
---

# PR Watch

## Before Starting

Read sibling rules, lessons, and gotchas when present. The `watch-pr` canonical
workflow is the public entry point. This skill owns the iteration contract;
debug and feedback skills own fix procedures.

## Iteration

One iteration is: check CI → check comments → route deltas → save `WATCH.md` and
the checkpoint. A fresh context must resume from those artifacts alone.

1. Run polling in a Light `fresh_subagent`; raw status/log payloads remain in
   that worker. Return only changed run IDs, brief failure evidence, new thread
   IDs, and a no-change marker.
2. Classify deltas on the main reasoning tier. Use bounded workers for fix
   engines and return compact SHAs, verification, replies, and residual risk.
3. When context thresholds fire, finish the iteration, update `WATCH.md`, use
   the checkpoint API, and apply `context_reset` or its declared fallback.
4. A provider `recurrence` binding may reinvoke the workflow. It must resume
   from `WATCH.md`, increment the durable iteration count, and preserve the same
   authorization and stop rules.

## Routing

- Transient infrastructure failure: rerun only the failed run, at most twice per
  run ID, then classify as real.
- Failure caused by the PR: run the bounded `fix-ci` path, verify, and reset the
  green streak.
- Pre-existing failure: record evidence; do not fix unrelated work.
- Bot or unambiguous local feedback: run feedback triage, fix/rebut with
  evidence, scrub PII, reply, and resolve within authorization.
- Ambiguous, architectural, cross-cutting, or conflict work: escalate without
  guessing or posting.

## Authorization Boundary

Invoking `watch-pr` grants standing authorization for fast-forward commits to
the PR branch and factual replies/resolution within the routed scope. It does
not authorize amend, rebase, force-push, other branches, merge, approval,
requesting changes, or expanded scope. Emit the visible Watch Started grant
before the first effect.

## Stops

Stop and persist `Status: escalated` when a failure group survives two fixes, a
history rewrite/conflict is needed, a human decision is required, three
distinct flaky resets occur, unrelated dirty work exists, or twelve cumulative
iterations complete without stability.

The watch is `stable` only when the green streak reaches its target, no comments
remain past the cursor, and no escalation remains. Default target is one green;
raise it to five after any flaky/transient failure unless the user explicitly
set another target.

## Recurrence Reachability

Before using `recurrence`, verify that the execution environment can reach the
repository API. Cloud-backed bindings are forbidden for VPN/IP-restricted repos;
use a VPN-connected local fallback and report that it only runs while the host
and VPN are available. Provider adapters own concrete scheduling syntax.
