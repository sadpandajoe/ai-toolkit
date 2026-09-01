---
tier: Heavy
---

# PR Review Procedure

Use for a single GitHub PR review after `review-pr` resolves the PR reference.

## Required Context

Read before grading: `rules/code-review.md` and `rules/severity.md`. Every lane
that dispatches from this file produces or triages severity-tagged code-review
findings, and the calibration in `rules/code-review.md` applies to every review
path — single-reviewer, adversarial, and multi-reviewer synthesis. The review
umbrella deliberately no longer supplies these (it is also carried by plan, PM,
and QA routes), so a lane whose closure contains no reviewer lens would
otherwise grade with no calibration contract at all.

## Gather Context

Fetch:

```bash
gh pr view <ref> --json title,body,author,baseRefName,headRefName,files,additions,deletions
gh pr diff <ref>
gh pr view <ref> --json files -q '.files[].path'
```

Read full contents of changed files. Review comments target changed lines, but the review must understand surrounding context.

## Complexity Gate

Classify the PR scope with the shared TRIVIAL / STANDARD / COMPLEX gate and this review-specific routing:

| Signal | Trivial | Standard | Complex |
|--------|---------|----------|----------|
| Files changed | 1-3 | 4-8 in one subsystem | 9+ or unclear ownership |
| Lines changed | < 100 | 100-400 | 400+ |
| Behavioral change | None / cosmetic | Contained functional change | Cross-cutting or contract change |
| Reviewer lanes | Code quality only | Triggered lanes only | Full triggered team, plus optional second opinion |

Emit the Complexity Gate block per `rules/complexity-gate.md`.

`review-pr --deep` (and the phrase "deep review PR #N") pins the tier to at
least COMPLEX before this table is read — size signals can raise that floor but
never lower it.

Trivial + certainty `Clear`: code quality review only, unless impact assessment escalates. Standard: triggered reviewer lanes only, with no premise deep-dive unless impact or uncertainty escalates. Complex: premise validation plus full triggered team.

## Assess Impact and Premise

Run [../../qa/references/assess-impact.md](../../qa/references/assess-impact.md) on the PR diff to classify impact as CORE, STANDARD, or PERIPHERAL.

Impact escalation:
- TRIVIAL + CORE -> code quality plus only the lens matching why the workflow is
  CORE. Use the full team only when multiple CORE lenses apply or the relevant
  safety lens is ambiguous.
- STANDARD + CORE -> triggered reviewer lanes plus stricter severity calibration
- COMPLEX + CORE -> full team + suggest adversarial review for security-sensitive areas

For Standard, CORE-impact, or low-confidence PRs, validate the premise before reviewing implementation details:
1. Read linked issue/ticket, PR description, author comments, and prior reviewer comments.
2. Investigate whether the stated problem exists.
3. For bug fixes, check whether the fix addresses the actual cause.
4. For features, check whether the feature solves the stated need and belongs in the chosen architecture.

If the premise is wrong, make that the primary finding and skip remaining review lanes. Still route it through the reasoning/confirmation flow before posting.

## Detect Review Team

Follow [classify-diff.md](classify-diff.md) with the diff and complexity tier. Pass the impact assessment to all reviewers so severity calibration can account for CORE workflows.

For Standard or CORE-escalated PRs, include pattern analysis:
- read 2-3 similar files in the same directory/module
- compare naming, error handling, imports, signatures, and local conventions
- flag convention deviations as `[minor]` with evidence

## Launch Review Lanes

`review.pr-moderate` and `review.pr-standard` each resolve to one reviewer
dispatch — there is no lens menu and no per-lens selection flag. The dispatch prompt
carries whichever lenses `classify-diff` triggered for this diff on top of
the boundary's fixed `rules/code-review.md` + `agents/codex/reviewer.md`
contracts; the single worker reads all of them and applies each in one pass,
the same way `review.pr-batch` applies its full lens set in one pass (see
SKILL.md's Invocation section).

Trivial:
<!-- aitk-model-route:review.pr-trivial -->
- Dispatch exactly one fresh code-quality reviewer on `review`. That single lane **is** the independent review — never zero, never a second lane, and never an orchestrator self-review in its place.
- If clean, return a compact approve recommendation. Post/approve only when `--auto` or explicit user authorization grants that boundary.

Standard:
<!-- aitk-model-route:review.pr-moderate -->
- One dispatch carrying only the triggered reviewer lenses needed by the diff
  classification. Triggered lenses come from this set: [code-quality.md](code-quality.md),
  [deep-quality.md](deep-quality.md),
  [adversarial.md](adversarial.md),
  [../../testing/references/review-tests.md](../../testing/references/review-tests.md),
  [../../testing/references/review-testplan.md](../../testing/references/review-testplan.md),
  [architecture.md](architecture.md),
  [frontend.md](frontend.md),
  [backend.md](backend.md).
  Code-judo is not one of them — it dispatches at its own boundary below.
- Keep the main thread compact: collect findings, recommendation, confidence, and any premise uncertainty.
- Escalate to Complex only when reviewers find cross-cutting risk, unclear ownership, or security-sensitive behavior.

Complex:
<!-- aitk-model-route:review.pr-standard -->
- One dispatch carrying every triggered reviewer lens, in the priority order
  from [classify-diff.md](classify-diff.md). Triggered lenses come from the
  same set listed under Standard, above. Code-judo is not one of them — it
  dispatches at its own boundary below.
- Use `review` for bounded PR passes and `deep-review` for architecture,
  security-sensitive, adversarial, or substantial multi-system diffs.
- Optional second opinion when available.
- Include the adversarial lens whenever `--adversarial` is passed or
  security-sensitive content is detected. Its findings are severity-tagged, so
  they merge with the rest of the pass's findings rather than getting their
  own section — that split belongs to Code-judo alone. On a TRIVIAL PR the
  flag escalates the tier to Standard, because TRIVIAL runs a single pass with
  no room for an extra lens; security-sensitive detection escalates to
  Complex under the existing rule.

<!-- aitk-model-route:review.pr-cross-provider-cold -->
Standard and Complex PR reviews also dispatch a cross-provider cold reviewer as a separate stage: run `bin/aitk model-run --provider <cross-provider>` on the `review.pr-cross-provider-cold` boundary with PR scope and diff only — never the origin pass's findings. Verify each `[major]`/`[minor]` with a lane from a different family than the one that raised it (a different provider in deep review mode), and keep `provider/family` provenance on every finding through dedup into the report.

**Deep review mode.** When `classify-diff` reports **Deep-tier escalation: YES**
(`ultra`/`max` effort, `--deep`, or a deep-tier phrase — `classify-diff` owns
the phrase list), follow the review SKILL's *Deep review mode* section: pin the
tier to at least COMPLEX, route every triggered lens through `deep-review` —
both `review.pr-moderate` and `review.pr-standard` permit it — and run the
cross-provider cold lane on `deep-review`.

**Code-judo lane.** Dispatch the code-judo generative pass separately via
`review.code-judo` whenever `classify-diff` reports **Code-judo lane: YES** *and*
the dispatching caller did not pass `Batch mode: Code-judo suppressed` — which a
`^refactor` PR title or an explicit ask can set on its own, with
`Deep-tier escalation: NO`. Do not gate judo dispatch on the escalation field.
Code-judo returns unscored restructuring **proposals**; surface them in their own
section, not the scored findings/component table.

When the payload carries `Batch mode: Code-judo suppressed` (set by the batch
orchestrator in [pr-batch.md](pr-batch.md)), skip the judo lane even
on `Code-judo lane: YES`,
run the findings lenses only, and record the proposals slot as
`suppressed (batch)` rather than `none`.

If the cross provider is unreachable on a Complex or deep review, the review
**blocks**: report the resolver's disclosure and stop, or continue only on
explicit user override with the disclosure retained in the output. A
single-provider run is never reported as a deep review.

## Synthesize Findings

Merge findings from all lanes and deduplicate, organized by component so the summary stays scannable:

| Component | Meaning |
|-----------|---------|
| Root Cause | Why was this change needed? |
| Solution | Is it efficient, maintainable, and scoped? |
| Tests | Are tests realistic and meaningful? |
| Code | Is it readable, consistent, and correct? |
| Docs | Are docs/comments sufficient? |

Use `rules/code-review.md` and `rules/severity.md`.

Before posting findings, show the user:
- issue and proposed severity
- why this severity
- confidence
- evidence

Clean reviews skip the reasoning review and proceed to posting rules.

## Recommendation

- **Approve**: zero `[major]` findings
- **Request Changes**: any unresolved `[major]` finding
- **Comment**: no `[major]`, but notable `[minor]` findings worth the author's attention before merge

## Output

Return the synthesized review plus:
- recommendation
- team selected, with each lane's route and `provider/family`
- resolved `Model coverage:` level, and the resolver's disclosure sentence whenever it returns one (below floor, dropped lane, or no diverse verifier)
- finding counts, each finding carrying raiser and verifier `provider/family`
- posting mode needed (`draft`, `confirm`, `auto`)

Findings posted to GitHub carry severity and evidence only. Model provenance
stays in the local report and PROJECT.md record — it is orchestration detail,
not review-comment content.
