# Model and Effort Assignment

Only the parent reads this file. `interfaces/model-routing.json` is the only
source of truth for routes, model selectors, provider controls, and effort
(README's model table is generated from it); skills name stable routes and
launch specialists with `bin/aitk model-run`.

- Prefer the other provider for review and validation; the parent's own
  provider through `model-run` is the disclosed fallback.
- Never downgrade: a missing provider, rejected selector, or malformed result
  makes the route unavailable. Never retry on a cheaper family, and never
  substitute a generic worker for a routed specialist.
- The `planning` route plans only COMPLEX work; STANDARD work is planned
  inline. The deep routes are read-only advisors and never implement.
- `xhigh` (a deep route) only on a classifier flag or after the standard route
  stayed materially uncertain; never `max` automatically.
- Hotfix and P1 work enters specialists earlier; safety gates stay strict.
- Promoting a new model changes its selector in
  `interfaces/model-routing.json` and its price in `aitk/pricing.py`.
