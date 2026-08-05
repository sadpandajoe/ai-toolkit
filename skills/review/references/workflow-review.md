---
tier: Heavy
---

# Capability-Orchestrated Review (Standard Tier)

Use for `review-code` and `review-pr` when the Complexity Gate is STANDARD or
when at least three independent reviewer lanes trigger.

## Capability Contract

1. The main thread gathers base SHA, changed files, acceptance criteria,
   preflight result, and triggered lens references, then resolves the tier
   roster per [ensemble.md](ensemble.md) (`standard`, or `deep` in deep review
   mode, or `security` for the security panel). Record the resolved coverage
   level before dispatching anything.
2. Use `parallel_fanout` with at most six **findings** lanes **on the origin
   provider**. Each lane runs in a `fresh_subagent`, reads the actual diff, and
   returns only schema-shaped findings: severity, file, line, title, detail,
   proof, suggested fix, and the lane's `provider/family` provenance. Follow the
   lens priority order in [classify-diff.md](classify-diff.md) when more than six
   lanes trigger, and `log` what was shed rather than silently truncating.
3. Concurrently, dispatch the ensemble's **cross-provider lane** as a separate
   stage. It is a cold whole-diff review: it receives scope and diff only, never
   the origin lanes' findings, and it does not consume the six-lane lens budget.
   The six-lane cap is per fan-out stage, not per review.
4. Fan in every lane before deduplication. Keep the highest severity for
   overlapping file/line/title findings, and **merge — never drop — the
   `provider/family` provenance** of every lane that raised each finding.
   A finding raised independently by both providers is marked convergent.
5. Use `parallel_fanout` again to adversarially verify every major/minor finding
   in fresh context. A verifier must read the cited code and attempt to refute
   the claim, and must come from a different model family (or, at `deep` and
   `security`, a different provider) than the lane that raised the finding.
   Verification lanes are their own stage with their own budget. Nitpicks may
   pass through without a verifier. When no diverse verifier is available, mark
   the finding unverified — never let the originating model confirm itself.
6. Return confirmed and refuted arrays only, each carrying raiser and verifier
   provenance. The main thread writes durable review state, applies fixes,
   re-verifies, and emits the Review Gate including the `Model coverage:` line.
   On **`review-code`** that hand-back has one more step: run the
   **resolved-state audit** at the `review.local-resolved-audit` boundary once
   the local fix queue is drained. It is mandatory on that path
   ([local-review.md](local-review.md)), so it belongs in this list — an
   off-thread fan-out that enumerates the remaining main-thread steps and omits
   it is how the lane silently stops running on exactly the reviews that require
   it. On **`review-pr`** it does not run: that boundary's contract reads the
   local Review Record and fix queue, and a PR review writes neither, so
   requiring it there names a step whose inputs do not exist. The PR path closes
   out by posting per [pr-posting.md](pr-posting.md) instead.

## Bounds

- The classifier selects lenses; never run all lenses by default.
- **Code-judo runs outside this fan-out.** The code-judo generative pass is never
  one of the six findings lanes and does not pass through dedup or adversarial
  verification — its output is unscored, behavior-preserving *proposals*, not
  severity findings. Dispatch it separately via the `review.code-judo` boundary
  whenever `classify-diff` reports `Code-judo lane: YES` — in deep review mode or
  from a `^refactor` title or explicit ask alone — *and* the dispatching caller
  did not pass `Batch mode: Code-judo suppressed` ([pr-batch.md](pr-batch.md)),
  which is the sole exception. Route its proposals to a dedicated Restructuring
  Proposals section of the Review Record; never coerce them into the
  schema-shaped findings pipeline.
- A security-sensitive finding uses the `security` ensemble's three-vote panel,
  which spans both providers. Do not approximate it with three lanes on one
  model.
- When a provider is unreachable, apply the ensemble's degraded-coverage action:
  `standard` continues with the disclosure sentence; `deep` and `security` block
  pending explicit user override. Never substitute another model for the missing
  one, and never describe a single-provider run as ensemble coverage.
- Provider adapters may execute fan-out sequentially only through the declared
  fallback; they may not weaken fresh-context or evidence requirements.
- Raw worker transcripts never become durable state. Confirmed findings and a
  compact refutation summary are the only fan-in artifacts.
