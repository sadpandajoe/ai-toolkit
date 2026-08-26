---
name: code-review
description: Use when you want a code review of local changes (uncommitted, staged, or committed) or a PR diff — covers what review-code, review-code-adversarial, and review-pr do today. Do NOT use for plan-level review (skills/plan-review), bug fixing (skills/goals/fix-bug), CI failures (skills/goals/fix-ci), or feature work (skills/goals/create-feature) — this skill only reviews code that has already changed.
---

# Code Review

## Before Starting

Read `rules/gates.md` first — it defines the six-state gate contract this
skill's skip and completion paths use. This skill is the v2 goal-skill entry
point for code review; it delegates the actual review procedure to
`skills/review/references/sol-review.md` and
`skills/review/references/delta-review.md` rather than reimplementing
dispatch — read both before continuing, since this skill's steps assume their
Inputs/Procedure/Output shape.

## Scope

**In scope:** normalize the review target (a local diff or a PR), determine
author identity, skip cleanly when there is nothing to review, run
`sol-review.md`'s procedure — which escalates to `delta-review.md` on its own
trigger conditions — and record the outcome.

**Out of scope:** plan-level review, which stays `skills/plan-review`'s own
reviewers — never dispatch this skill against a plan artifact. Also out of
scope: fixing what review finds beyond validating and applying
`sol-review.md`'s own findings — a broader fix belongs to
`skills/goals/fix-bug` or `skills/goals/fix-ci` instead.

## Steps

1. Normalize the review target:
   - **Local diff** — uncommitted, staged, or committed changes, optionally
     scoped to specific files or paths (mirrors
     `skills/workflows/references/review-code.md`'s `--files`/`--committed`/
     `--uncommitted` usage patterns).
   - **PR** — a PR number or URL (mirrors
     `skills/workflows/references/review-pr.md`'s scope).
2. If the normalized target has zero changes, emit a gate block under gate
   name `review` with `Reason: no changes to review`, per `rules/gates.md`'s
   Mapping From the Old Mechanisms section (`rules/review-gate.md`'s
   `Status: skipped` maps to `PASS` with the skip reason), and stop — no
   reviewer dispatch.
3. Determine author identity for `sol-review.md`'s Inputs: when this skill
   runs as an internal phase dispatched by another goal skill, use the
   identity of the worker that produced the change (e.g.
   `implementation-worker`), passed through by the caller. When invoked
   standalone against the user's own local changes with no worker of record,
   use `user` — `sol-review.md`'s independence check only needs an identity
   distinct from the reviewer, and `user` satisfies that trivially.
4. Follow `sol-review.md`'s procedure in full — Dispatch, Validate findings
   before fixing, Gate and record, Escalate only when triggered — passing the
   Scope from step 1, the Author identity from step 3, and any Acceptance
   criteria the caller supplied. Do not restate its dispatch steps here; this
   skill delegates rather than reimplementing them. Its own step 4 escalates
   to `delta-review.md` when triggered — no separate step is needed for that
   here.
5. Once the `review` gate block from `sol-review.md` (and `delta-review.md`,
   if escalated) reaches `PASS`: record a completion entry on `PROJECT.md`
   and summarize the findings for the user (applied, or dropped with a
   one-line reason), mirroring `review-code.md`'s Summary Contract. A `PASS`
   gate is a checkpoint, not license to stop before this step — see
   `rules/gates.md`'s Continuation Rule.

## Output

The `review` gate block — either step 2's skip, or `sol-review.md`'s (and
`delta-review.md`'s, if escalated) — followed by a short summary of findings
once it reaches `PASS`.

## Notes

- This skill is dual-run alongside `skills/workflows/references/review-code.md`,
  `review-code-adversarial.md`, and `review-pr.md` today; nothing dispatches
  "review my code"/"review this PR" requests here yet. The dual-run router
  pointer that makes this skill a live dispatch target lands in a later
  commit. Reading and testing it does not change live behavior.
- Declares no dispatch boundaries of its own — `review.sol-review` and
  `review.delta-review`, declared when those files were added (C38/C39),
  cover every model dispatch this skill's procedure reaches.
