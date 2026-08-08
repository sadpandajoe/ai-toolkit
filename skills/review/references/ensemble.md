---
tier: Standard
---

# Review Ensembles (tiered model diversity)

The roster for each review tier is data, not prose. Resolve it — never
hand-pick models:

```
<toolkit-root>/bin/aitk review-ensemble <tier> --provider <origin> [--available <providers>] [--cross-provider] --json
```

`<origin>` is the provider this session is running on. `--available` lists the
provider CLIs actually reachable; omit it only when both are known good.
`--cross-provider` engages the cross lanes of an `optional` tier; `required`
tiers engage them unconditionally and ignore the flag.

`--cross-provider` is **not** the independent second-opinion capability. The
second-opinion / independent-review capability lanes are same-provider `review`
lanes bolted onto a review; `--cross-provider` engages the *other provider's*
cold lane from this tier's roster. The two names are not interchangeable.

## Tiers

| Tier | Lens lanes | Mandatory lens routes | Cross-provider lane | Verification |
|------|-----------|-----------------------|---------------------|--------------|
| `trivial` | 1 | `review` | forbidden | none |
| `moderate` | up to 4 | `review` **+** `deep-review` | optional (opt-in) | 1 lane, different family |
| `standard` | up to 6 | `review` **+** `deep-review` | **required** | 1 lane, different family |
| `deep` | up to 6 | `deep-review` | **required** | 1 lane, different provider |
| `security` | up to 2 | `deep-review` | **required** (plus origin `review` third vote) | 2 lanes, different provider |

Rules the resolver enforces, and orchestrators must not reinterpret:

- **Lens routes are mandatory, not a menu.** Every route in the tier's roster
  carries at least one lens lane. The lane budget is an upper bound on
  concurrency, not permission to skip a route — a MODERATE run that fires only
  `review` lanes has not achieved the `family-diverse` coverage the resolver
  reported, because that level is derived from the roster's routes. If the
  triggered lens set leaves a route empty, assign a lens to it (deep-quality is
  the default `deep-review` lens — its Route cell in the review SKILL's lens
  table says `deep-review` for exactly this reason) or report the reduced level
  explicitly.
- **Lens lanes fan out on the origin provider only.** The cross-provider lane is
  a separate cold review of the whole diff, not a per-lens mirror. It does not
  consume the lens budget.
- **The lane budget is per fan-out stage.** Lens fan-out, verification fan-out,
  and the cross-provider lane are distinct stages; each is bounded on its own.
- **Cross lanes are cold.** The cross-provider reviewer receives the diff and
  scope, never the origin lanes' findings, so its agreement is evidence rather
  than an echo.
- **`optional` means opt-in, not automatic.** MODERATE stays provider-local
  unless the user or workflow passes `--cross-provider`; only `required` tiers
  engage the cross provider on their own. Without this the escalation ladder
  collapses — MODERATE and STANDARD would resolve to the same roster.
- **Verification stays inside the engaged roster.** The verifier pool is drawn
  from the providers this tier actually engaged, so a provider-local tier does
  not quietly reach across for its verifier.
- **A dropped lane is always disclosed.** If a requested lane was unavailable,
  the run reports `degraded` with the disclosure sentence even when the coverage
  floor is still met — asking for a cross-provider lane and not getting one is
  never reported as full coverage.
- **An unverifiable roster is disclosed too.** When no lane in the pool can meet
  the tier's diversity rule for some roster lane, the resolver names those lanes
  and reports `degraded` rather than `full`. A Codex-origin MODERATE hits this:
  Codex ships one model family, so family diversity is unreachable without
  `--cross-provider`, and findings from those lanes stay unverified.

## Verifier diversity

A finding is verified by a lane from a **different model family** than the lane
that raised it (`standard`/`moderate`), or from a **different provider**
(`deep`/`security`). Never let the originating model confirm its own finding.
When no lane satisfies the rule, record the verification as unverified — do not
substitute the originating model.

Resolve verifiers with `select_verifiers()`, which returns up to the tier's
verification-lane count, all satisfying the diversity rule and all distinct. It
returns fewer when the roster cannot supply that many, and the Review Record
reports the actual vote count.

The `security` tier's two verification lanes are the ceiling the catalog can
actually reach, not a lowered bar: Codex ships one model family, so a
Claude-raised finding has exactly two provider-diverse verifiers available. The
tier contracts for two so a full run means what it says. Never pad a panel back
to three by reusing the originating model or double-counting one lane — the
three-lane figure describes the *panel roster* (origin deep, cross deep, origin
third vote), which is a different count from the verifiers.

## Provenance

Every finding carries `provider/family` from the lane that raised it, and
`provider/family` of its verifier, from raise through dedup to the final report.
Deduplicating two lanes' overlapping findings merges the provenance lists; it
never drops them.

## Coverage vocabulary

| Level | Meaning |
|-------|---------|
| `provider-diverse` | Lanes ran on ≥2 providers |
| `family-diverse` | One provider, ≥2 model families |
| `single-family` | No diversity |

Report the resolved level verbatim on the `Model coverage:` line of the Review
Gate. When the level is below the tier's floor:

- `continue` / `disclose` tiers proceed and **must** print the resolver's
  disclosure sentence. Never describe such a run as ensemble or multi-model
  coverage.
- `block` tiers (`deep`, `security`) stop and report the blocked disclosure.
  Continue only on an explicit user override, and keep the disclosure in the
  Review Gate.

Never substitute a different model for an unavailable one, and never count the
parent session's own model as a diverse lane — the toolkit pins what it requests
but cannot attest the provider's internal serving-model identity.
