---
tier: Heavy
---

# Dispatch

Tier routing, deep review mode, and the Code-judo exception for the review
umbrella (`skills/review/SKILL.md`). Read this when actually dispatching
reviewer lenses, not when locating which reference covers a role.

Reviewer lens references are subagent prompts. Orchestration and posting references are read by the main thread.

Dispatch mode is tier-routed. Every tier resolves its roster from
[ensemble.md](ensemble.md) — the model/provider mix is
data, never a per-run judgment call:

| Tier | Ensemble | Dispatch |
|------|----------|----------|
| TRIVIAL | `trivial` | One `fresh_subagent` code-quality lens on `review`. That single lens **is** the independent review — no second reviewer, and no orchestrator self-review in its place. |
| MODERATE | `moderate` | `fresh_subagent` per triggered lens, all on the origin provider. The cross-provider lane is opt-in (`--cross-provider`), not automatic — MODERATE is provider-local by default, verification included. |
| STANDARD (or ≥3 triggered lanes) | `standard` | `parallel_fanout` per [workflow-review.md](workflow-review.md): lens fan-out → cold cross-provider lane → dedup → model-diverse adversarial verify. A cross-provider lane is **required**; losing it is disclosed reduced coverage, not a silent downgrade. |
| Deep review mode | `deep` | As STANDARD, with every lens on `deep-review`, a cross-provider `deep-review` cold lane, and provider-diverse verification. Blocks when the cross provider is unreachable. |
| Security / adversarial | `security` | Three-vote panel spanning both providers per [adversarial-orchestration.md](adversarial-orchestration.md). Blocks when the cross provider is unreachable. |

Only confirmed findings return to the session, each carrying the
`provider/family` that raised it and the one that verified it.

The lens fan-out boundaries (`review.local-primary-lanes`, `review.pr-moderate`,
`review.pr-standard`, `review.pr-lenses`, `review.local-final-pass`) declare a
`lenses` menu, so each dispatch must name its lens: resolve one route per
triggered lens with `--lens <repo-relative lens path>`. Resolving a fan-out
boundary without `--lens` fails closed rather than handing a single reviewer all
seven sibling lens contracts. Boundaries with no menu — the Code-judo lane, the
independent-capability lanes, and `review.pr-batch` — take no `--lens`. A menu is
what makes a lane fan out; `lens_domain` is separate and says only which artefact
the lane grades, so `review.pr-batch` carries a domain without a menu: it applies
its lenses itself, in one context, and its findings are graded as code all the
same.

## Deep review mode (tier override)

Deep review mode is entered on `ultra`/`max` effort, `--deep`, or a **deep-tier phrase** — `classify-diff` owns that phrase list (see its *Deep-tier phrases* section) and reports the verdict as `Deep-tier escalation: YES`. Do not re-derive the phrase set here. Note that a bare "deep quality" ask is *not* one of those phrases: it requests the deep-quality lens alone, not this tier override.

Deep review mode is an explicit **escalation**, not a route name. It is defined by three simultaneous effects, and a run that delivers fewer than all three is not a deep review:

1. **Tier pinned to at least STANDARD.** A small diff does not demote a deep review to TRIVIAL/MODERATE handling; the Complexity Gate still decides *which* lenses trigger, but the tier floor and the ensemble come from the escalation.
2. **Every triggered lens routes through `deep-review`**, and the Code-judo lane is added. Escalation is *sufficient* to add that lane but not necessary — the lane also fires on a `^refactor` title or an explicit Code-judo ask with escalation `NO`, so dispatch it on `Code-judo lane: YES`.
3. **Cross-provider review is mandatory** — the `deep` ensemble's cold whole-diff lane on the other provider, plus provider-diverse verification. When the other provider is unreachable, the review **blocks** with the resolver's disclosure rather than continuing as a single-provider run.

The lens dispatch boundaries (`review.local-primary-lanes`, `review.pr-standard`, `review.pr-moderate`, `review.code-quality-final`, `review.pr-lenses`) all permit `deep-review` in their allowlists, and the cross-provider lane uses each workflow's own cold-review boundary (`review.local-cross-provider-cold`, `review.pr-cross-provider-cold`, `review.adversarial-cross-provider-panel`) — so this is route and provider selection, not a new binding. The independent second-opinion / independent-review *capability* lanes are external capabilities rather than lenses — they stay on their own `review` route, on the origin provider, and do not escalate. They are not the ensemble's cross-provider lane: "second opinion" means one more fresh lane on the same provider, while `--cross-provider` engages the other provider's cold lane from the tier roster.

The three overlapping names mean different things and are not synonyms:
`deep-review` is a **route** (a model + effort pinning), `review-pr --deep` /
"deep review PR #N" is this **mode** (tier floor + routes + cross-provider
ensemble), and `review-code-adversarial` is a **workflow** that runs the
`security` ensemble.

## Code-judo (deep tier)

The `code-judo` lens is the one exception to tier-routing: it is pinned to the deep tier regardless of the diff's complexity **and regardless of whether deep review mode is active**. Whenever `classify-diff` reports `Code-judo lane: YES` — including on an otherwise standard-tier `^refactor`-titled change with `Deep-tier escalation: NO` — it runs on the `deep-review` route per [code-judo.md](code-judo.md) — the generative restructuring pass always runs on the deepest reasoning tier, never the standard `review` route. The `review.code-judo` boundary allows only `deep-review`, so a mistaken standard-route request fails closed rather than silently downgrading the model.

**Batch exception.** Multi-PR batch review ([pr-batch.md](pr-batch.md))
is the one documented exception: it runs the findings lenses only and suppresses
the judo pass even on `Code-judo lane: YES`. Because each per-PR review sees only
its own payload, the batch orchestrator must include the literal line
`Batch mode: Code-judo suppressed` in that payload; a payload without it follows
the default rule above. `classify-diff` still reports the lane truthfully — the
exception lives in the caller, not the classifier.

Run Code-judo **outside** the six-lane findings fan-out (see [workflow-review.md](workflow-review.md)): its output is unscored restructuring *proposals*, not severity-tagged findings, so it bypasses the dedup + adversarial-verification pipeline and lands in a dedicated **Restructuring Proposals** section of the Review Record rather than the findings table.
