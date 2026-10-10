---
name: implement-change
description: Use when implementing one accepted plan slice, phase, or RCA fix as a bounded patch with its tests, returning a compact handoff for parent verification and review. Do NOT use for investigation, unapproved scope, planning, or standalone review.
---

# Implement Change

## Required Context
Read before starting: `rules/implementation.md`, `rules/testing.md`

## Contract

Implement exactly one accepted unit: the narrowest patch that satisfies its exit
criteria, with regression protection, handed back for parent-run verification
and independent review. This is the contract the toolkit's implementer agent
and the routed `implementation` specialist both execute. As a worker you run
without a person watching, so nobody can answer a question mid-task: make the
routine judgment calls inside the unit yourself and note them in the handoff.

1. Check entrance criteria; stop and report if unmet.
2. Test first per the mode the plan named: RED/GREEN regression test for a
   bug, acceptance test set for a feature. If a test cannot run here, write it
   and record the gap.
3. Implement the minimum change; follow existing patterns; no new abstractions
   the unit does not need.
4. Run the acceptance command and tests for changed files; report exact
   commands and observed results. A syntax-only check, or a command that
   failed to start, is not a result: report that check as not run, and why.
5. Never commit, push, amend, rebase, or stage. Never edit `PROJECT.md`,
   `PLAN.md`, or workflow manifests. Never widen scope; report out-of-scope
   needs as residual risk. The commit, push, and amend lines in
   `rules/implementation.md` describe what the parent does after verification
   and review, not what a worker does.
6. The same approach failing twice is `blocked`, not a third variation.

## Output

Return the compact handoff from `rules/specialist-handoff.md` as
`## Handoff: implementer`. When the route runner enforces a structured result,
the handoff goes in `summary` and the commands you ran, with their results, in
`verification`. The parent runs the verification loop, updates the routing
snapshot and `PROJECT.md`, and owns any authorized git action.
