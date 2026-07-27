---
tier: Heavy
---

# Local Code Review Orchestration

Use for `review-code` on local uncommitted, staged, committed, or path-filtered changes.

## Gather Changed Files

Default scope is **branch-wide**: combine `<base>..HEAD` (committed) with `git diff --name-only` and `git diff --cached --name-only` (uncommitted). This avoids the common re-invocation where a user reviews a branch and the first pass only sees uncommitted work.

- `--committed`: only `<base>..HEAD`.
- `--uncommitted`: only working tree and staged changes (legacy behavior).
- Path args or `--files`: filter to requested files.
- Read full content for changed files plus the relevant diff.

<!-- aitk-model-route-exempt:pre-dispatch-condition -->
Before dispatching reviewers, print a one-line scope summary so the user can intervene early:

```
Scope: <N> committed + <M> uncommitted files (<base>..HEAD = <short-sha>..HEAD)
```

Stop if no changes are found in the resolved scope.

## Complexity Gate

Classify scope with `rules/complexity-gate.md` and this review-specific routing:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Files changed | 1-2 | 2-4 in one subsystem | 5+ or unclear ownership |
| Lines changed | < 50 | 50-200 | 200+ |
| Logic changes | None or cosmetic | Contained functional change | Cross-cutting behavior |
| Reviewer lanes | Code quality only | Triggered lanes only | Full triggered team |

The independent second-opinion capability runs on **every** tier when available, independent of this table.

Formatting-only diffs and micro-fixes may skip the review loop under `rules/review-gate.md`.

## Classify + Impact

Run these in parallel when possible:

- [classify-diff.md](classify-diff.md): choose reviewer domains.
- [../../qa/references/assess-impact.md](../../qa/references/assess-impact.md): classify functional impact as CORE, STANDARD, or PERIPHERAL.

Escalate CORE impact:

- TRIVIAL + CORE: run code-quality plus **only the reviewer lens that matches why the change is CORE** (e.g., security/auth → adversarial; data-loss/migration → backend; hooks/safety → code-quality alone is sufficient). Escalate to the full team only when multiple CORE lenses apply or the safety-relevant lens is ambiguous. The point of CORE is calibration, not fan-out.
- MODERATE + CORE: run triggered reviewer lanes and escalate any security-sensitive or data-loss risk to Standard handling.
- STANDARD + CORE: run full team and suggest adversarial review for security-sensitive areas.
- CORE test gaps use stricter severity calibration.

## Pre-Flight Verification

Run the repo's relevant checks before reviewer dispatch:

- Build/typecheck/lint when applicable.
- Tests covering changed files or changed behavior when they are quick enough for the review scope.
- A clear skipped reason when the app or suite is not runnable locally.

<!-- aitk-model-route-exempt:pre-launch-condition -->
If pre-flight fails, fix the failure or report it as a blocker before launching reviewer lanes. Reviewer context should include the pre-flight result.

## Dispatch Reviewers

Routine bounded lanes use `review`. Architecture, security, adversarial, and
high-risk final lanes use `deep-review`. Resolve and launch the route through
`<toolkit-root>/bin/aitk model-route --boundary <marker-id>` and matching
`model-run`; an unrouteable lane is
unavailable and must not silently fall back to a generic worker.

**STANDARD tier (or ≥3 triggered lanes): dispatch via [workflow-review.md](workflow-review.md)** — lens fan-out, dedup, and adversarial verification run off-thread; the main thread ingests only confirmed findings, then resumes at the Review Record step below. TRIVIAL/MODERATE continue with direct spawns:

<!-- aitk-model-route:review.local-primary-lanes -->
The main thread is an orchestrator. Dispatch fresh-context reviewer subagents on `review`/`deep-review` with:

- Diff and full changed-file contents.
- Acceptance criteria from PROJECT.md if relevant.
- Complexity and impact assessment.
- Pre-flight verification result.
- The selected reviewer reference.

Use triggered references from `classify-diff.md`, including:

- [code-quality.md](code-quality.md)
- [deep-quality.md](deep-quality.md) — strict structural findings; default lane on STANDARD-tier diffs
- [../../testing/references/review-tests.md](../../testing/references/review-tests.md)
- [../../testing/references/review-testplan.md](../../testing/references/review-testplan.md)
- [../../plan-review/references/architecture.md](../../plan-review/references/architecture.md)
- [../../plan-review/references/frontend.md](../../plan-review/references/frontend.md)
- [../../plan-review/references/backend.md](../../plan-review/references/backend.md)

`classify-diff` reports two independent fields; read each one separately, and follow the review SKILL's *Deep review mode* and *Code-judo* sections:

- **Deep-tier escalation: YES** — route every triggered lens through `deep-review` instead of its default route.
- **Code-judo lane: YES** — dispatch the [code-judo.md](code-judo.md) generative pass separately (outside the findings fan-out) via the `review.code-judo` boundary. Its proposals go in the Restructuring Proposals section, not the findings table.

These do not imply each other. A `^refactor`-titled change or an explicit Code-judo ask sets `Code-judo lane: YES` with `Deep-tier escalation: NO` — dispatch the judo pass anyway (still on `deep-review`, which that boundary pins) while the findings lenses stay on their default routes.

<!-- aitk-model-route:review.local-independent-second-opinion -->
Launch the **Independent Second Opinion** capability (see below) concurrently with these reviewer spawns — it is an independent reviewer, not a post-pass.

Collect findings from all primary lanes and the independent lane, dedupe, sort by severity, and write the Review Record to PROJECT.md before fixing `[major]` and `[minor]` issues or checkpointing.

## Re-Verify + Iterate

After applying reviewer fixes, re-run relevant checks:

- Build/typecheck/lint.
- Tests covering changed files or changed behavior.
- Targeted verification for fixed findings.

If checks fail, fix and re-run classification/review as needed.

### Final Pass After Fix Queue

When the fix queue introduced new code paths (not just deletions, one-line reverts, or check-driven fixes), spawn **one additional fresh-eyes review pass on the integrated diff** before emitting the Review Gate. Frame the prompt explicitly as "final pass on the integrated state, not a re-read of the original diff."

Trigger signals (any one is enough):
- ≥2 fix-queue items added new branches, helpers, fixtures, or guard clauses.
- A major fix introduced a producer/consumer pair where one side was tested but not both.
- A fix added a marker file, sentinel, or other artifact that needs symmetric cleanup elsewhere in the codebase.
- A bug-fix during validation duplicated an existing helper into a second location without a sync mechanism.

Skip the final pass only when **all** fix-queue items were: pure deletions, one-line reverts, formatting, or comment-only.

<!-- aitk-model-route:review.local-final-pass -->
Use fresh reviewer subagents on `deep-review` for the final pass — never the ones who reviewed the original diff. Its scope is `base..HEAD` of the integrated branch, not the fix-queue commits in isolation. If the final pass surfaces majors, treat them as a new review round and iterate.

## Independent Second Opinion (capability-based)

Every `review-code` run requests an independent review in addition to the primary reviewer lanes on all tiers that run the review loop. The lane degrades gracefully and never blocks the review.

<!-- aitk-model-route:review.local-independent-capability -->
Launch the runtime's configured `independent-review` capability on `review` concurrently with reviewer dispatch. Provider adapters own discovery, authentication, and invocation; this shared skill owns only the stable input and output contract. Pass one of these scopes:

- default branch-wide → `auto`
- `--committed` → `branch`, with the selected base
- `--uncommitted` → `working-tree`

The adapter returns normalized findings with `severity`, `file`, `line`, `evidence`, and `recommendation`. If the capability is unavailable or errors, record `Independent review: skipped (unavailable)` in the Review Gate and continue with the primary lanes.

Map independent findings into the toolkit severity scale, then dedupe against the primary lanes:

- Must fix / critical → `[major]`
- Should fix / improvement → `[minor]`
- Style/preference → `[nitpick]`

Fix new `[major]` issues and verify again. Surface **independent-only** findings (those no primary lane flagged) explicitly in the Review Record so cross-reviewer divergence stays visible.

The whole-loop skip for formatting-only and micro-fix diffs (per `rules/review-gate.md`) skips this lane too — there is no diff worth a second opinion.

## Review Gate

Emit after all review lanes finish:

```markdown
## Review Gate
Rounds: [N]
Pre-flight: [pass/fail/skipped]
Independent review: [clean/findings (N) /skipped (unavailable) /skipped (micro-fix)]
Status: [clean/blocked/user decision/skipped/micro-fix]
```

## PROJECT.md Review Record

Write or update this compact record before fixing findings or clearing context. Keep only actionable state; do not paste full reviewer transcripts.

```markdown
## Current Code Review

**Scope:** <changed files or path filter>
**Pre-flight:** <pass/fail/skipped — command or reason>
**Review Gate:** <pending/clean/blocked/user decision/skipped/micro-fix>

### Findings
| ID | Severity | File | Finding | Status |
|----|----------|------|---------|--------|
| R1 | major/minor/nitpick | path:line | concise issue | open/fixed/deferred/user-decision |

### Restructuring Proposals
<!-- Only when a code-judo pass ran (`Code-judo lane: YES` — deep review mode is one way in, a `^refactor` title or explicit ask is another). These are unscored, behavior-preserving proposals, not severity findings — never fold them into the Fix Queue automatically. Omit the section entirely when no judo pass ran or it found no move. -->
- P1 — <one-line restructuring> — deletes <what>, reframing <how>; behavior-preservation risk: <the one weak point>.

### Fix Queue
- [ ] R1 — <specific next action>

### Resume Notes
- Next: <fix R1 / re-run verification / emit Review Gate / continue caller workflow>
```

If there are no actionable findings, write `Findings: none` and the clean Review Gate status so checkpoint + context_reset can resume without reconstructing review context from chat.

## Summary

Use the standalone summary only when `review-code` is user-invoked directly. Internal callers own their next-step section.

```markdown
## Review-Code Complete
Rounds: [N] | Pre-flight: [pass/fail/skipped] | Status: [clean/blocked]

### Team Selected
| Reviewer | Why |
|----------|-----|

### Fixed
- [...]

### Test Coverage
- [...]

### Remaining
- [...]
```
