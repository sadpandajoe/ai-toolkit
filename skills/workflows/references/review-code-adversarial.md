# Adversarial Red-Team Review

> **When**: You want to stress-test changes for security holes, edge cases, race conditions, and failure modes.
> **Produces**: Adversarial findings with concrete scenarios, fixes or evidence-based rejections, verification, and a review gate.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

`review-code-adversarial` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`.

## Usage

```bash
review-code-adversarial [--committed] [<path>]
review-code-adversarial --allow-degraded   # accept a same-provider lane when the other provider is down
```

## Procedure

Ensure a routing snapshot exists before any gate is recorded: `bin/aitk
project-state init --workflow review-code-adversarial --complexity
<classified> --size <S|M|L|XL>` when none exists; an owning workflow's
snapshot stays as it is (`init` refuses a different workflow without
`--replace`).

1. Discover changed files as in
   [skills/review/references/local-review.md](../../review/references/local-review.md)
   (recorded base, full file contents, preflight).
2. Run the primary adversarial lane.
   <!-- aitk-model-route:workflows.adversarial-primary -->
   Launch one fresh adversarial reviewer worker on `deep-review` using
   [skills/review/references/adversarial.md](../../review/references/adversarial.md),
   preferring the other provider, with scope, diff, and full files only. If
   the other provider is unreachable the gate is `BLOCKED (degraded)`; only
   `--allow-degraded`, recorded as `USER_DECISION`, lets a same-provider lane
   stand in, and the report names it.
3. Add the second vote only for security-sensitive diffs or an explicit ask.
   <!-- aitk-model-route:workflows.adversarial-second-opinion -->
   Launch one more fresh adversarial reviewer worker on `deep-review` with the
   same [adversarial.md](../../review/references/adversarial.md) lens on the
   provider the primary did not use; it receives scope and diff only, never the
   primary's findings. Under `--allow-degraded` with one provider the second
   vote is skipped and the report says so; without the override there is no
   degraded run to skip it from.
4. Merge findings: both lanes agree → high confidence, keep severity; one lane
   only → validate against the code before promoting past `[minor]`. Drop
   findings whose `file:line` is outside the diff. Sort: vulnerability, race,
   data integrity, missing validation, edge case.
5. Fix, reject with evidence, or surface as `USER_DECISION` for every concrete
   finding; verify with `skills/verification-loop/SKILL.md`; one delta pass on
   the fixed files through the adversarial lens when fixes were substantive.
6. Record the gate with `bin/aitk project-state gate --gate review --status
   <...> --result <envelope> --format block` (one `--result` per lane's
   `model-run` envelope) and paste the `## Gate: review` block it prints, with
   `Adversarial rating: Hardened | Adequate | Vulnerable | Critical` (derived
   from accepted findings: Critical for an accepted security `[major]`,
   Vulnerable for any other accepted `[major]`, Adequate for `[minor]` only,
   Hardened for none), `Reviewers: <lanes as provider/family>`, and the
   accepted/raised tally as its `--evidence`. A gate that is not recorded, or
   a PASS without the envelopes, does not count, and
   `hooks/require-review-gate.sh` refuses `gh pr create` without it. Write `## Adversarial Findings` and `## Adversarial Fix Round N` to
   `PROJECT.md` before any fixes and after each round.

## Gates

- Every finding needs a concrete failure scenario.
- Never claim two-lane coverage when one lane ran.
- Rounds follow `rules/gates.md`: one full pass, one delta, then escalate.
