---
name: pr-watch
description: Babysit an open PR by monitoring CI and review comments, routing bounded fixes, and escalating decisions. Use for a durable watch-pr run. Do NOT use for one-off CI diagnosis, a single feedback round, or reviewing someone else's PR.
---

# PR Watch

The `watch-pr` canonical workflow is the public entry point. This skill is
the one home of the watch's authorization, iteration contract, stops and
recurrence; debug and feedback skills own fix procedures.

## Iteration

One iteration is: check CI → check comments → route deltas → save `WATCH.md` and
the checkpoint. A fresh context must resume from those artifacts alone.

1. The parent computes the delta: checks from `statusCheckRollup` (external
   status contexts included) whose state changed, and thread IDs new since
   the `WATCH.md` cursor, or a no-change marker. There is no polling worker.
   Classification and diagnosis stay with the main thread or an
   `rca`/`deep-rca` worker.
2. Classify deltas on the main reasoning tier. Use bounded workers for fix
   engines and return compact SHAs, verification, replies, and residual risk.
3. When context thresholds fire, finish the iteration, update `WATCH.md`, use
   the checkpoint API, and continue in a fresh worker or session.
4. A provider `recurrence` binding may reinvoke the workflow. It must resume
   from `WATCH.md`, increment the durable iteration count, and preserve the same
   authorization and stop rules.

Between checks, wait with a background or scheduled wait when the harness
offers one, otherwise a bounded blocking poll. Before each rerun or reply,
`bin/aitk project-state op --check rerun:<run-id>` (or `reply:<thread-id>`)
skips one a crashed session already made; record it after with `op --id`.
When an iteration changed something (a fix, a rerun, a reply, an escalation),
tell the user briefly what changed and the current streak; an idle iteration
needs no message. The watch runs unattended: between stops, keep iterating
instead of ending the turn with a plan, a status update, or a question. A
session that ends mid-watch leaves `Status: watching` in `WATCH.md`, and the
PROJECT.md checkpoint names the resume target.

## Routing

- Transient infrastructure failure: rerun only the failed GitHub Actions jobs
  (`gh run rerun <run-id> --failed`), at most twice per run ID, then classify
  as real. A failed external status context cannot be rerun from here: it is
  classified like any failure, and a transient one is reported and waited on,
  or escalated.
- Failure caused by the PR: run the bounded `fix-ci` path, verify, and reset the
  green streak.
- Pre-existing failure: record evidence; do not fix unrelated work.
- Bot or unambiguous local feedback: run feedback triage, fix/rebut with
  evidence, scrub PII, reply, and resolve within authorization. Replies to
  humans stay factual ("Done in `<sha>`").
- Ambiguous, architectural, cross-cutting, or conflict work: escalate without
  guessing or posting.

Each fix keeps its engine's own gates (classification, verification strength,
review gate, PII scrub), and pushes only on `STRONG` verification; a `PASS
(downstream: CI)` is recorded and the next iteration reads CI as the verifier.

## Authorization Boundary

Invoking `watch-pr` grants standing authorization for fast-forward commits to
the PR branch and factual replies/resolution within the routed scope. It does
not authorize amend, rebase, force-push, other branches, merge, approval,
requesting changes, or expanded scope. The invocation is the commit
confirmation; emit the visible Watch Started grant before the first effect,
and again on resume.

## Stops

Stop and persist `Status: escalated` when a failure group survives two fixes, a
history rewrite/conflict is needed, a human decision is required, three
distinct flaky resets occur, unrelated dirty work exists, or twelve cumulative
iterations complete without stability. Repeated flaky failures go to
infrastructure, not to more test hardening
([skills/debug/lessons.md](../debug/lessons.md)).

The watch is `stable` only when the green streak reaches its target, no comments
remain past the cursor, and no escalation remains. An iteration is green only
when every rollup entry for the head SHA, Actions and external, has passed. Default target is one green;
raise it to five after any flaky/transient failure unless the user explicitly
set another target.

## Recurrence Reachability

Before using `recurrence`, verify that the execution environment can reach the
repository API. Cloud-backed bindings are forbidden for VPN/IP-restricted repos;
use a VPN-connected local fallback and report that it only runs while the host
and VPN are available. Provider adapters own concrete scheduling syntax.

The GitHub API for Preset's repos — `superset-shell`, `superset-private`, `manager` — is reachable **only from the corporate VPN**. Jenkins mirrors build status back onto the PRs as commit statuses, but reading any of it still needs VPN-level API access.

Consequence for automation: **anything cloud-executed cannot read these repos.** A
cloud-backed `recurrence` binding runs off the VPN and cannot authenticate to the
API. Do not recommend it for workflows that must read a Preset repo (PR
watching, CI polling, release audits).

Automation that must read these repos runs **locally** on a host connected to the VPN: an in-session recurrence capability or a local scheduler invoking the provider's headless runner. A local runner only fires while the machine is awake and VPN-connected, so scheduled runs must report missed/offline executions rather than silently implying coverage.

Public repos (e.g. the toolkit's own) are unaffected; cloud scheduling is fine there.
