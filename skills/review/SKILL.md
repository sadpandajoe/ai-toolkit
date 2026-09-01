---
name: review
description: "Use for reviewing implemented code through orchestration, classification, reviewer lenses, and PR helpers. Do NOT use for plan review, root-cause investigation, or implementation."
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

## Required Context

Read before starting: `rules/gates.md`. That is the only contract *every*
lane on a review route shares. The grading contracts (code-review, severity)
belong to the individual findings lenses and are named in each lens
file's own Required Context — deliberately not here, and deliberately without
backticked paths, because anything this section names is inlined into every lane
that resolves through this umbrella. That includes the generative Code-judo lane
and the non-code-review routes (QA validation, PM brief review, plan review)
that also carry this file.

Umbrella for code-review work — review of *shipped code*, not plans. References
are grouped by role so workflows load only the phase they are entering.

## Orchestration

| Reference | Role |
|-----------|------|
| [references/sol-review.md](references/sol-review.md) | Default: one independent SOL review pass, findings validated before fixing |
| [references/delta-review.md](references/delta-review.md) | Triggered-risk escalation beyond the default pass (security-sensitive surface, deep-tier phrase, or explicit ask) |
| [references/local-review.md](references/local-review.md) | Local `review-code` orchestration |
| [references/pr-review.md](references/pr-review.md) | Single GitHub PR review procedure |
| [references/pr-batch.md](references/pr-batch.md) | Batch PR review orchestration |
| [references/adversarial-orchestration.md](references/adversarial-orchestration.md) | `review-code-adversarial` orchestration |
| [references/workflow-review.md](references/workflow-review.md) | Standard-tier capability orchestration (lens fan-out → dedup → adversarial verify) |

## Classifiers

| Reference | Role |
|-----------|------|
| [references/classify-diff.md](references/classify-diff.md) | Read diff + complexity tier, return which reviewer domains should activate |

## Posting Helpers

| Reference | Role |
|-----------|------|
| [references/pr-posting.md](references/pr-posting.md) | GitHub review posting and summary rules |

## Reviewer Lenses

| Lens | When | Reference | Route |
|------|------|-----------|-------|
| Code quality | Always (every complexity tier) | [references/code-quality.md](references/code-quality.md) | review |
| Deep quality | Refactor-shaped or COMPLEX diff, deep review mode, a bare "deep quality" lens ask, **or** whenever the tier's mandatory `deep-review` route would otherwise carry no lane. Strict structural **findings**. Routed by `classify-diff`. | [references/deep-quality.md](references/deep-quality.md) | deep-review |
| Code-judo | `classify-diff` reports `Code-judo lane: YES` — deep review mode, a `^refactor`-titled change, or an explicit Code-judo ask. Generative restructuring **proposal** (runs outside the findings fan-out). Pinned deep tier — see Invocation. | [references/code-judo.md](references/code-judo.md) | deep-review |
| Adversarial | Security-sensitive diffs; `review-code-adversarial` workflow | [references/adversarial.md](references/adversarial.md) | deep-review |

## Distinction vs Other Umbrellas

- **review/** (this skill) — reviews code (post-implementation); its architecture/frontend/backend lenses are dual-purpose and also back plan review (pre-implementation) via `agents/codex/plan-validator.md`
- **testing/** — includes `review-tests` + `review-testplan` (test-harness-specific reviewers)
- **qa/** — scenario-level critique (bug triage, validation)

The `review-code` workflow dispatches through `classify-diff`, which chooses lenses from this umbrella **and** the `testing/` umbrella when tests are in scope.

<!-- aitk-model-route:review.pr-lenses -->
The `review-pr` workflow uses `pr-review`, `pr-batch`, and `pr-posting` for PR-specific context gathering and GitHub interaction, then dispatches the same reviewer lenses on `review`/`deep-review` as `review-code`:

- [references/code-quality.md](references/code-quality.md)
- [references/deep-quality.md](references/deep-quality.md)
- [references/adversarial.md](references/adversarial.md)
- [../testing/references/review-tests.md](../testing/references/review-tests.md)
- [../testing/references/review-testplan.md](../testing/references/review-testplan.md)
- [references/architecture.md](references/architecture.md)
- [references/frontend.md](references/frontend.md)
- [references/backend.md](references/backend.md)

Those lanes grade shipped code, so they read `rules/code-review.md` and
`rules/severity.md` before scoring. The lens files that carry code-review tags
name both themselves; the three dual-purpose lenses above are reused here on
code rather than on a plan, so this boundary supplies the calibration they
would otherwise lack. Naming it in this span rather than in Required Context
above keeps it out of the non-code-review routes that also carry this umbrella.

Code-judo is not in that fan-out: it dispatches at the `review.code-judo`
boundary, which carries its own contract closure.

## Invocation

Reviewer lens references are subagent prompts. Orchestration and posting references are read by the main thread.

Dispatch defaults to [references/sol-review.md](references/sol-review.md): one
independent SOL review pass, findings validated before fixing. A diff that
carries a security-sensitive surface, a deep-tier phrase, or an explicit
caller ask escalates to [references/delta-review.md](references/delta-review.md)
in addition to that pass — never in place of it.

<!-- aitk-model-route-exempt:describes-boundary-not-dispatch -->
Every dispatch boundary resolves to exactly one `fresh_subagent` reviewer
pass — there is no lens menu and no per-lens fan-out. A boundary's declared
`contracts` are the fixed set of lens files that single pass reads and applies
in one context: `review.pr-batch`, for instance, carries eight lens contracts
and grades all of them itself in one dispatch rather than spawning eight
lanes. The five orchestration references above (`local-review.md`,
`pr-review.md`, `pr-batch.md`, `workflow-review.md`,
`adversarial-orchestration.md`) each resolve their own fixed boundary this
way. `classify-diff` still decides *which* lenses are in scope for a given
diff — TRIVIAL/STANDARD/COMPLEX gates which checks apply — but the tier no
longer selects a roster of separate runs; it is one pass, one context, per
boundary. `lens_domain` says only which artefact kind that pass grades
("code" or "plan"), independent of how many lens contracts it carries.

Only confirmed findings return to the session, each carrying the
`provider/family` that raised it and the one that verified it.

### Deep review mode (tier override)

Deep review mode is entered on `ultra`/`max` effort, `--deep`, or a **deep-tier phrase** — `classify-diff` owns that phrase list (see its *Deep-tier phrases* section) and reports the verdict as `Deep-tier escalation: YES`. Do not re-derive the phrase set here. Note that a bare "deep quality" ask is *not* one of those phrases: it requests the deep-quality lens alone, not this tier override.

Deep review mode is an explicit **escalation**, not a route name. It is defined by three simultaneous effects, and a run that delivers fewer than all three is not a deep review:

1. **Tier pinned to at least COMPLEX.** A small diff does not demote a deep review to TRIVIAL/STANDARD handling; the Complexity Gate still decides *which* lenses trigger, but the tier floor comes from the escalation.
2. **Every triggered lens routes through `deep-review`**, and the Code-judo lane is added. Escalation is *sufficient* to add that lane but not necessary — the lane also fires on a `^refactor` title or an explicit Code-judo ask with escalation `NO`, so dispatch it on `Code-judo lane: YES`.
3. **Cross-provider review is mandatory** — a cold whole-diff pass on the other provider, plus provider-diverse verification. When the other provider is unreachable, the review **blocks** with the resolver's disclosure rather than continuing as a single-provider run.

The lens dispatch boundaries (`review.local-primary-lanes`, `review.pr-standard`, `review.pr-moderate`, `review.code-quality-final`, `review.pr-lenses`) all permit `deep-review` in their allowlists, and the cross-provider lane uses each workflow's own cold-review boundary (`review.local-cross-provider-cold`, `review.pr-cross-provider-cold`, `review.adversarial-cross-provider-panel`) — so this is route and provider selection, not a new binding. The independent second-opinion / independent-review *capability* lanes are external capabilities rather than lenses — they stay on their own `review` route, on the origin provider, and do not escalate. "Second opinion" means one more fresh lane on the same provider; the cross-provider cold lane above is a separate, mandatory pass on the other provider.

The three overlapping names mean different things and are not synonyms:
`deep-review` is a **route** (a model + effort pinning), `review-pr --deep` /
"deep review PR #N" is this **mode** (tier floor + routes + mandatory
cross-provider pass), and `review-code-adversarial` is a **workflow** that
runs the security panel in [references/adversarial-orchestration.md](references/adversarial-orchestration.md).

### Code-judo (deep tier)

The `code-judo` lens is the one exception to tier-routing: it is pinned to the deep tier regardless of the diff's complexity **and regardless of whether deep review mode is active**. Whenever `classify-diff` reports `Code-judo lane: YES` — including on an otherwise standard-tier `^refactor`-titled change with `Deep-tier escalation: NO` — it runs on the `deep-review` route per [references/code-judo.md](references/code-judo.md) — the generative restructuring pass always runs on the deepest reasoning tier, never the standard `review` route. The `review.code-judo` boundary allows only `deep-review`, so a mistaken standard-route request fails closed rather than silently downgrading the model.

**Batch exception.** Multi-PR batch review ([references/pr-batch.md](references/pr-batch.md))
is the one documented exception: it runs the findings lenses only and suppresses
the judo pass even on `Code-judo lane: YES`. Because each per-PR review sees only
its own payload, the batch orchestrator must include the literal line
`Batch mode: Code-judo suppressed` in that payload; a payload without it follows
the default rule above. `classify-diff` still reports the lane truthfully — the
exception lives in the caller, not the classifier.

Run Code-judo **outside** the six-lane findings fan-out (see [references/workflow-review.md](references/workflow-review.md)): its output is unscored restructuring *proposals*, not severity-tagged findings, so it bypasses the dedup + adversarial-verification pipeline and lands in a dedicated **Restructuring Proposals** section of the Review Record rather than the findings table.

## Notes

- `classify-diff` has a different shape from the reviewer references (it's a classifier, not a reviewer). Grouped here because reviewer dispatch is the head of the review workflow.
- Reviewer lens descriptions declare their own reasoning-load hints in frontmatter for subagent spawning.
