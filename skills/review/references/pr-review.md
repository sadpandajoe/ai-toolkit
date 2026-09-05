# PR Review Procedure

Use for a single GitHub PR after `review-pr` resolves the reference.

## Gather Context

```bash
gh pr view <ref> --json title,body,author,baseRefName,headRefName,files,additions,deletions
gh pr diff <ref>
```

Read the full contents of changed files. Fetching and posting are main-thread
actions; review lanes are read-only and receive the material inline.

## Classify and Assess

Emit the Complexity Gate (`rules/complexity-gate.md`) using the PR signals
below, run [classify-diff.md](classify-diff.md), and run
`qa/references/assess-impact.md`.

| Signal | TRIVIAL | STANDARD | COMPLEX |
|---|---|---|---|
| Files changed | 1-3 | 4-8, one subsystem | 9+ or unclear ownership |
| Behavioral change | None or cosmetic | Contained | Cross-cutting or contract change |
| Deep lenses | Only on flags | Only on flags | Flags plus premise validation |

`--deep` or a deep-tier phrase pins complexity to at least COMPLEX and routes
the independent review on `deep-review`.

**Premise validation** (COMPLEX or CORE impact): read the linked issue, PR body,
and prior comments; confirm the stated problem exists and the change addresses
its cause or need. A wrong premise is the primary finding; skip the remaining
lanes and go to posting.

## Independent Review

<!-- aitk-model-route:review.pr-independent -->
Launch one fresh reviewer worker on `review` (or `deep-review` under `--deep`),
on the other provider when reachable, with the PR title and body, the diff and
full changed files, the classifier's flags and impact, and any premise notes.
Never include earlier review rounds or other reviewers' comments; the lane must
be cold. The worker receives its contract inline from the route runner. If no
cross-provider lane is reachable, use the toolkit's same-provider reviewer agent
and disclose it in the report, except under `--deep` or a security-sensitive
flag: there the review is `BLOCKED (degraded)` until the other provider is
reachable or the user passes `--allow-degraded`, recorded as `USER_DECISION`
(`rules/gates.md`, Independent Judgment). Single-source `[major]` findings are
verified before posting exactly as in `local-review.md`.

## Deep Lenses (conditional)

<!-- aitk-model-route:review.pr-deep-lenses -->
When the classifier flagged risk, launch at most two additional fresh worker
lanes on `deep-review`, one per flagged lens, resolved with `--lens`:
[adversarial.md](adversarial.md) for security sensitivity or `--adversarial`,
[deep-quality.md](deep-quality.md) for refactor shape or a deep-quality ask, or
[../../plan-review/references/architecture.md](../../plan-review/references/architecture.md)
for architecture changes. A code-judo ask runs at its own boundary
([code-judo.md](code-judo.md)) and its proposals stay in their own section.

## Synthesize

Dedupe findings, then validate each `[major]` and `[minor]` against the diff
before recording it (`rules/code-review.md`). Recommendation:

- **Approve**: no `[major]`, and any `[minor]` is non-blocking.
- **Request changes**: any accepted `[major]`.
- **Comment**: only `[minor]` findings that should be addressed.

Before posting, show the user each finding with severity, why, confidence, and
evidence unless `--auto` was passed. Then follow
[pr-posting.md](pr-posting.md).

## Output

The synthesized review, the recommendation, the independent lane and deep
lenses that ran (`provider/family`), accepted/raised counts, and the posting
mode (`draft`, `confirm`, `auto`). Model provenance stays in the local report
and `PROJECT.md`; posted comments carry severity and evidence only.
