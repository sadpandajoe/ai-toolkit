---
tier: Heavy
---

# Capability-Orchestrated Review (Standard Tier)

Use for `review-code` and `review-pr` when the Complexity Gate is STANDARD or
when at least three independent reviewer lanes trigger.

## Capability Contract

1. The main thread gathers base SHA, changed files, acceptance criteria,
   preflight result, and triggered lens references.
2. Use `parallel_fanout` with at most six **findings** lanes. Each lane runs in a
   `fresh_subagent`, reads the actual diff, and returns only schema-shaped
   findings: severity, file, line, title, detail, proof, and suggested fix. A
   full-stack STANDARD review (code quality, deep quality, architecture, tests,
   frontend, backend) fills exactly six. If a seventh findings lane would trigger
   (e.g. an adversarial lane stacked onto a full team), shed the lowest-value
   lane for this diff — drop an untouched-subsystem lane first, then
   legibility-only coverage — and `log` what was dropped rather than silently
   truncating.
3. Fan in every lane before deduplication. Keep the highest severity for
   overlapping file/line/title findings.
4. Use `parallel_fanout` again to adversarially verify every major/minor finding
   in fresh context. A verifier must read the cited code and attempt to refute
   the claim. Nitpicks may pass through without a verifier.
5. Return confirmed and refuted arrays only. The main thread writes durable
   review state, applies fixes, re-verifies, and emits the Review Gate.

## Bounds

- The classifier selects lenses; never run all lenses by default.
- **Code-judo runs outside this fan-out.** In deep review mode the code-judo
  generative pass is not one of the six findings lanes and does not pass through
  dedup or adversarial verification — its output is unscored, behavior-preserving
  *proposals*, not severity findings. Dispatch it separately via the
  `review.code-judo` boundary and route its proposals to a dedicated
  Restructuring Proposals section of the Review Record; never coerce them into
  the schema-shaped findings pipeline.
- A security-sensitive finding may use a three-vote independent panel.
- Provider adapters may execute fan-out sequentially only through the declared
  fallback; they may not weaken fresh-context or evidence requirements.
- Raw worker transcripts never become durable state. Confirmed findings and a
  compact refutation summary are the only fan-in artifacts.
