---
tier: Heavy
---

# Workflow-Orchestrated Review (Standard Tier)

Use for `/review-code` and `/review-pr` when the Complexity Gate resolves **STANDARD** (or when ≥3 reviewer lanes trigger at MODERATE+CORE). For TRIVIAL and MODERATE scopes, keep direct Agent-tool spawns per [local-review.md](local-review.md) — workflow overhead isn't justified below ~3 lanes.

## Why a Workflow Here

At Standard tier the orchestrator otherwise pays a main-thread round-trip per lens spawn and per returned finding set, and dedup happens in-context. The Workflow moves find → dedup → verify off-thread: lenses return schema-validated findings, dedup runs in plain JS, each deduped finding gets an adversarial verification pass, and only **confirmed** findings re-enter the session. Total tokens go up (each agent pays its own setup); orchestrator context stays thin and false positives die before they reach the fix queue.

**Authorization:** this reference instructing the Workflow call is the explicit opt-in — invoking `/review-code` or `/review-pr` at Standard tier sanctions the orchestration. No separate user confirmation needed.

## Script Shape

The orchestrator gathers scope (base SHA, changed-file list, acceptance criteria, pre-flight result, triggered lenses from `classify-diff.md`) and passes them via `args`. Lens agents read the diff themselves (`git diff <base>..HEAD -- <files>`) — keep spawn prompts to pointers, not payloads.

```js
export const meta = {
  name: 'standard-tier-review',
  description: 'Lens fan-out, dedup, adversarial verify; returns confirmed findings',
  phases: [{ title: 'Review' }, { title: 'Verify' }],
}
const FINDINGS = { type: 'object', required: ['findings'], properties: { findings: { type: 'array', items: {
  type: 'object', required: ['severity', 'file', 'title', 'detail', 'proof'],
  properties: { severity: { enum: ['major', 'minor', 'nitpick'] }, file: { type: 'string' },
    line: { type: 'number' }, title: { type: 'string' }, detail: { type: 'string' },
    proof: { type: 'string', description: 'how the cited line was confirmed, e.g. "read locally" or "verified via gh api" — not "from PR description"' },
    suggested_fix: { type: 'string' } } } } } }
const VERDICT = { type: 'object', required: ['refuted', 'reason'], properties: {
  refuted: { type: 'boolean' }, reason: { type: 'string' } } }

phase('Review')
const raw = (await parallel(args.lenses.map(l => () =>
  agent(`${l.context}\n\nReview per the lens reference at ${l.referencePath} (read it first). ` +
        `Diff: git diff ${args.base}..HEAD -- <changed files>. Pre-flight: ${args.preflight}. ` +
        `Each finding must cite a file:line you actually read and set "proof" to how you confirmed it ` +
        `(read locally / verified via gh api) — never a claim synthesized from the PR description. ` +
        `Apply the finding calibration in rules/code-review.md: a finding whose line is not in the diff is out of scope; ` +
        `sibling-path symmetry caps at minor. Return findings only — no prose.`,
    { label: `lens:${l.key}`, phase: 'Review', schema: FINDINGS })
))).filter(Boolean).flatMap(r => r.findings)

// Barrier justified: dedup needs all lenses' findings before paying for verification.
// dedupe keeps highest severity on file+line+title overlap; a finding surfaced by ≥2 lenses is
// convergent (high confidence, keep severity), a single-lens finding stays candidate until verified.
const deduped = dedupe(raw)

phase('Verify')
const verified = await parallel(deduped.map(f => () =>
  f.severity === 'nitpick' ? Promise.resolve({ ...f, confirmed: true })
  : agent(`Adversarially verify this review finding — try to REFUTE it by reading the actual code. ` +
          `Finding: ${f.title} at ${f.file}:${f.line}. Detail: ${f.detail}. ` +
          `Refuted=true if the code already handles it, the path is unreachable, or the claim misreads the diff.`,
      { label: `verify:${f.file}`, phase: 'Verify', schema: VERDICT })
      .then(v => ({ ...f, confirmed: v && !v.refuted, refute_reason: v?.reason }))
))
return { confirmed: verified.filter(f => f.confirmed), refuted: verified.filter(f => !f.confirmed) }
```

## Bounds

- ≤6 lenses per round; lens set comes from `classify-diff.md`, never "all lenses by default".
- 1 verifier per major/minor finding; escalate to a 3-vote panel only for security-sensitive findings (adversarial lens active). Nitpicks pass through unverified.
- Lens and verifier agents inherit the session model — judgment work never downgrades to a check tier (one misclassification costs more than the spawn saves).
- Fix application, re-verification, and the [final pass after fix queues](local-review.md#final-pass-after-fix-queue) stay with the main thread per local-review.md. A final pass that itself hits Standard-tier signals may reuse this workflow with fresh lenses.

## After the Workflow Returns

The main thread owns durable state, exactly as in [local-review.md](local-review.md):

1. Write the `## Current Code Review` record to PROJECT.md from `confirmed` (refuted findings get one summary line — count + reason class — not table rows).
2. Build the fix queue from confirmed majors/minors; proceed per local-review.md (fix, re-verify, final pass, Review Gate).
3. The workflow result is the orchestrator's only ingestion point — never re-read lens transcripts into the main thread.
