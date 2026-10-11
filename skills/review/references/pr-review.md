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

Emit the Complexity Gate (`rules/complexity-gate.md`), run
[classify-diff.md](classify-diff.md), and run
`qa/references/assess-impact.md`. The PR signal is the behavioural change:
none or cosmetic is TRIVIAL, contained is STANDARD, cross-cutting or a
contract change is COMPLEX. Deep lenses run only on flags at every tier.

`--deep` or a deep-tier phrase pins complexity to at least COMPLEX and routes
the independent review on `deep-review`.

**Premise validation** (COMPLEX or CORE impact): read the linked issue, PR body,
and prior comments; confirm the stated problem exists and the change addresses
its cause or need. A wrong premise is the primary finding; skip the remaining
lanes and go to posting.

## Lanes

Launch the lanes `bin/aitk review plan --kind pr --pr <ref> --parent <your
provider> --complexity <tier> --impact <impact>` lists (add `--deep`,
`--adversarial`, `--security-sensitive`, `--architecture`, or `--refactor`
when they apply). It applies the second-family triggers, the two-lens cap,
the provider and family for each lane, and `BLOCKED (degraded)`, which stands
until the other provider is reachable or the user passes `--allow-degraded`,
recorded as `USER_DECISION` (`rules/gates.md`, Independent Judgment). Every
lane is cold: the PR title and body, the diff and full changed files, the
classifier's flags and impact, and any premise notes, never earlier review
rounds or other reviewers' comments. Each runs through `bin/aitk model-run`
with the boundary, route, provider, and lens the plan names.

<!-- aitk-model-route:review.pr-independent -->
Launch one fresh reviewer worker on `review` (or `deep-review` under `--deep`)
for the plan's `independent` lane. The worker receives its contract inline from
the route runner.

<!-- aitk-model-route:review.pr-second-family -->
Launch one more fresh reviewer worker on `review` (`deep-review` under
`--deep`) for the plan's `second-family` lane (COMPLEX or CORE impact), on the
provider the independent lane did not use, through `bin/aitk model-run`. It
spends the other family's quota, which is why STANDARD PRs stay at one lane.

<!-- aitk-model-route:review.pr-deep-lenses -->
For each deep-lens lane, launch one fresh worker on `deep-review` resolved
with `--lens`: [adversarial.md](adversarial.md) for security sensitivity or
`--adversarial`, [deep-quality.md](deep-quality.md) for refactor shape or a
deep-quality ask, or
[architecture.md](architecture.md) for architecture changes. A code-judo ask runs at its own boundary
([code-judo.md](code-judo.md)) and its proposals stay in their own section.

## Synthesize

Run `bin/aitk review merge --result <lane>=<envelope> …` to dedupe by
file:line, compute convergence, and list the single-source majors that need a
verifier on the other family. Then validate each `[major]` and `[minor]`
against the diff before recording it (`rules/code-review.md`), exactly as in
`local-review.md`: a single-source `[major]`, a reviewer-reported missing flag,
and lane yields are handled there. Recommendation:

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
