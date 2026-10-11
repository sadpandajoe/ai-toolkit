# Model and Effort Assignment

Only the parent reads this file. `interfaces/model-routing.json` is the only
source of truth for model selectors, provider controls, and effort; skills
name stable routes and launch specialists with `bin/aitk model-run`.

| Route | When |
|---|---|
| `implementation` | Substantial edits and tests, from an accepted artifact |
| `planning` | COMPLEX architecture decomposition or a COMPLEX phase plan, read-only |
| `review` | The one independent code, plan, or PR review |
| `deep-review` | Adversarial, architecture, or security lens on flagged risk; exceptional escalation |
| `rca` | Independent RCA validation when the parent's hypothesis is uncertain |
| `deep-rca` | Competing causes, intermittent or cross-system failures, after `rca` stayed uncertain |
| `operations` | Read-only evidence reduction and deterministic reports |

- Prefer the other provider for independent review and validation; review on
  the parent's provider through `model-run` is the fallback and is disclosed.
  Deep lenses follow the same preference, with the parent's own deep family as
  the second vote and the single-provider verifier fallback.
- Fable plans only COMPLEX work; STANDARD work is planned inline. The deep
  routes are read-only advisors and never implement.
- Never downgrade: a missing provider, rejected selector, or malformed result
  makes the route unavailable. Never retry on a cheaper family, and never
  substitute a generic worker for a routed specialist.
- Effort comes from the route. `xhigh` (a deep route) only on a classifier
  flag or after the standard route stayed materially uncertain; never `max`
  automatically.
- Hotfix and P1 work enters specialists earlier; quality outranks token
  savings there, and safety gates stay strict.
- Promoting a new model changes its selector in
  `interfaces/model-routing.json` and its price in `aitk/pricing.py`; route
  names and skills stay stable.
