---
name: delta-review
description: Run one additional triggered-risk deep review pass when a diff carries a security-sensitive surface, a deep-tier escalation phrase, or an explicit caller request beyond sol-review's baseline pass. Internal helper, escalated to from sol-review.md -- never runs standalone as the only review. Do NOT use for the baseline single-pass review (sol-review's job) or for plan-level review (skills/workflows/references/review-plan.md's own dispatch).
user-invocable: false
disable-model-invocation: true
---

# Delta Review

Shared procedure for the one additional, triggered-risk review pass that
[sol-review.md](sol-review.md) escalates to — never a second independent lane
run by default, and never a return to the ensemble's tier-resolved multi-lane
roster.

## When this runs

Only when `sol-review.md`'s step 4 has already triggered escalation:

- **Security-sensitive surface** — per `classify-diff.md`'s step 4 signal
  list (auth/authz, cryptographic ops, unsanitized input, SQL/ORM with dynamic
  input, secrets/credentials, permission checks, plus this repo's three
  infra-specific rows: agent capability configuration, worker context
  assembly, trust boundary changes). This procedure cites that list by
  reference and never restates it — `classify-diff.md` is its sole owner.
- **Deep-tier escalation** — one of `classify-diff.md`'s three canonical
  phrases ("deep review", "deep quality review", "thermonuclear"), or `max`/
  `ultra` effort. Same rule: cited, not copied.
- **Explicit caller request** for the deeper pass, independent of either
  signal above.

Refactor shape alone (`^refactor` title, structural churn) is advisory only —
it does not trigger this procedure by itself; see `code-judo.md`'s own
conservatism on that point. This procedure never runs standalone as the whole
review — it always follows a completed `sol-review.md` pass, adding to it
rather than replacing it.

## Inputs

Same scope, author identity, and acceptance criteria as the triggering
`sol-review.md` pass, plus:

- **Trigger reason** — which of the three conditions above fired, so the
  dispatch can be scoped (a security trigger needs the adversarial posture; a
  bare deep-tier-phrase or explicit-ask trigger does not).

## Procedure

### 1. Dispatch the triggered-risk pass

<!-- aitk-model-route:review.delta-review -->
Dispatch the `deep-review` route's reviewer worker again — the native
`deep-review-worker` (`agents/claude/deep-review-worker.md`) when that
boundary's `routed_subagent` binding is `native`, otherwise the Codex
`reviewer` contract (`agents/codex/reviewer.md`) — this time applying
`adversarial.md`'s red-team posture
(`skills/review/references/adversarial.md`) whenever the trigger was
security-sensitivity — construct a concrete triggering scenario per finding,
not abstract "could be fragile" reasoning, exactly as that file's Posture
Self-Check demands. For a deep-tier-phrase or explicit-ask trigger without a
security signal, the same reviewer pass runs at deep-tier depth without the
adversarial lens forced on. One additional pass, not a fan-out across
multiple lenses or providers — that roster is what `sol-review.md` already
replaced.

### 2. Validate findings before fixing

Same rule as `sol-review.md` step 2: the implementing side confirms each
finding is real and correctly severed (`rules/severity.md`) before fixing it,
and records a one-line reason for any finding it drops.

### 3. Gate and record

Record the outcome under the same `review` gate `sol-review.md` used — this
is one escalation within that gate, not a second gate. `aitk gate-state set`'s
repeat-failure counting (`aitk.gates.decide_failure`) only produces a
meaningful `ESCALATE` if both passes report through the same gate name.

## Output

- Additional findings, post-validation (applied, or dropped with a one-line
  reason)
- The (shared) `review` gate outcome, updated for this pass
- Confirmation of which trigger condition fired

## Constraints

- Never runs as the whole review — always additive to a completed
  `sol-review.md` pass.
- Do not re-derive `classify-diff.md`'s trigger predicates here; cite them.
- Do not fan out to multiple lenses/providers; this is one additional pass,
  not a return to the ensemble roster.

## Notes

- `skills/review/SKILL.md`'s Invocation section now documents
  [sol-review.md](sol-review.md) and this file as the default dispatch path
  (C40). The five orchestration references it lists (`local-review.md`,
  `pr-review.md`, `pr-batch.md`, `workflow-review.md`,
  `adversarial-orchestration.md`) still dispatch through
  [ensemble.md](ensemble.md)/[classify-diff.md](classify-diff.md)/the lens
  files internally, unchanged — that internal switch is not this commit's
  scope. Ensemble stays live and directly callable via
  `bin/aitk review-ensemble` until a full goal-skill review cycle has run on
  this pair (Wave 8).
