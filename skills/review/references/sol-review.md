---
name: sol-review
description: Run one independent SOL code review by default for a changed-code diff, then require the implementing side to validate each finding before applying it. Internal helper for local/PR/workflow review entry points. Do NOT use for plan-level review (skills/workflows/references/review-plan.md's own dispatch) or for a triggered-risk deep pass -- that is delta-review.md's job.
user-invocable: false
disable-model-invocation: true
---

# SOL Review

Shared procedure for producing one independent code review pass on a changed-
code diff, then requiring the side that made the change to validate each
finding before acting on it, rather than fanning out to a tier-resolved
multi-lane roster for the baseline case.

## When this runs

Whenever code (not a plan artifact) has changed and needs review: local
uncommitted/staged/committed changes, a PR diff, or any workflow-triggered
review dispatch. Never for plan-level review — that stays
`skills/workflows/references/review-plan.md`'s own dispatch. A triggered-risk
deep pass beyond this one full review is a separate, sibling procedure,
escalated to rather than looped here.

## Inputs

The caller provides:

- **Scope**: the diff or changed-file set to review
- **Author identity**: which worker produced the change (e.g.
  `implementation-worker`), so this procedure can assert independence
- **Acceptance criteria**, if any, from the originating plan or issue
- **Gate name** (optional): defaults to `review`. A caller looping this
  procedure per slice/wave/phase (e.g. `fix-bug`'s Complex or Multi-Phase
  Path) must pass a scoped name (`fix-bug-slice-2-review`,
  `fix-bug-phase-<phase name>-review`) — gate history is per `(gate, phase)`
  per `skills/verification-loop/SKILL.md`'s Notes, so reusing the bare
  `review` name across independent units would collapse their repeat counts
  together.

## Procedure

### 1. Dispatch one independent review

<!-- aitk-model-route:review.sol-review -->
Dispatch the `review` route's reviewer worker against the full scope in one
pass — not a per-lens fan-out: the provider's native `review-worker`
(`agents/claude/review-worker.md`) when the `routed_subagent` binding is
`native` for that boundary, otherwise the Codex `reviewer` contract
(`agents/codex/reviewer.md`), per `rules/specialist-handoff.md`. Never the
same identity that authored the change;
`aitk.gates.assert_independent_verification("implementation-worker",
"review-worker")` (or `"codex-reviewer"` on the shimmed path) is the
machine-checkable slice of that rule. Output is findings only
(file/line/severity/one-line rationale), per the dispatched contract's own
shape — no narrative.

### 2. Validate findings before fixing

The implementing side must validate each finding before applying it, not
apply findings mechanically:

- Confirm the finding is real against the actual code — not a hallucinated
  line or symptom.
- Confirm the severity is warranted, per `rules/severity.md`.
- Only then fix it.

A finding that does not hold up on inspection is dropped, with a one-line
reason recorded — never silently fixed and never silently discarded. This is
the source plan's explicit rule: independent reviewer, validate findings
before fixing, one full review plus a conditional delta/deep review.

### 3. Gate and record

Record the outcome via `aitk gate-state set` under gate name `review`, using
`aitk.gates`' six-state vocabulary (`PASS`/`RETRY`/`ESCALATE`/
`USER_DECISION`/`BLOCKED`/`RECLASSIFY`) — never a numeric threshold. `PASS`
requires every validated required finding to be resolved, not merely
reviewed.

### 4. Escalate only when triggered

If the diff carries a risk signal this one pass is not scoped to catch —
security-sensitive surface, an adversarial-relevant change, or a caller
explicitly requesting the deeper pass — escalate to
[delta-review.md](delta-review.md) rather than looping this same independent
pass again. Report the trigger reason (security-sensitive surface, deep-tier
phrase, or explicit ask) so that procedure can scope its dispatch.

## Output

- Review findings, post-validation (applied, or dropped with a one-line
  reason)
- The `review` gate outcome
- Any `RECLASSIFY`/`ESCALATE` reason, if validation surfaced one

## Constraints

- One full independent pass by default — do not fan out to multiple
  lenses or providers for the baseline case; that is what this procedure
  replaces.
- Never let the implementing identity review its own work;
  `assert_independent_verification` enforces identity, not correctness.
- Do not apply an unvalidated finding, and do not discard one without
  recording why.

## Notes

- `skills/review/SKILL.md`'s Invocation section documents this file as the
  single dispatch, with [delta-review.md](delta-review.md) as its escalation.
  The five orchestration references it lists (`local-review.md`,
  `pr-review.md`, `pr-batch.md`, `workflow-review.md`,
  `adversarial-orchestration.md`) each resolve their own fixed dispatch
  boundary directly — one reviewer pass per boundary, reading whichever lens
  contracts that boundary (and the triggered set from
  [classify-diff.md](classify-diff.md)) name, in one context. There is no
  ensemble table and no `review-ensemble` CLI subcommand any more.
