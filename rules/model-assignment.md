# Model and Effort Assignment

`interfaces/model-routing.json` is the only source of truth for volatile model
selectors, provider controls, and effort values. Skills name stable routes;
how a provider adapter dispatches a route depends on that provider's
`routed_subagent` binding in `interfaces/providers.json`. A `fallback`
binding resolves the route with
`<toolkit-root>/bin/aitk model-route --boundary <marker-id>` and launches it
with `<toolkit-root>/bin/aitk model-run --boundary <marker-id>`. A `native`
binding dispatches by name to a provider-native worker instead — see
`config/providers/claude.md`'s `routed_subagent` entry for which roles that
covers today.

| Route | Use | Effort | Codex family | Claude family |
|---|---|---|---|---|
| `implementation` | Normal bounded development | high | Sol | Sonnet |
| `review` | Bounded plan, code, test, or PR review | high | Sol | Opus |
| `deep-review` | Architecture, security, adversarial, or final cold review | xhigh | Sol | Fable |
| `rca` | Clear, bounded root-cause synthesis | high | Sol | Sonnet |
| `deep-rca` | Ambiguous, intermittent, historical, or cross-system RCA | xhigh | Sol | Fable |
| `operations` | Read-only evidence reduction and deterministic operational reporting after parent/tool collection | high | Sol | Sonnet |

Rules:

- Keep the main coding session on the user's current Sol-or-newer or Opus
  workhorse at high effort. Routes govern spawned workers, not the already
  active parent session.
- Codex development workers never go below the current Sol family. Claude
  `implementation` and `rca` workers use Sonnet; `review`, `deep-review`, and
  `deep-rca` stay on Opus/Fable so a stronger model always checks Sonnet's
  work. Sonnet must
  never review or gate-decide its own `implementation`/`rca` output — that
  invariant is enforced mechanically by `rules/gates.md`'s six-state contract,
  which routes every non-`PASS` outcome back through a `review`/`deep-review`
  worker, never back through the same Sonnet route that produced the work.
- Sonnet on `implementation`/`rca` may execute tests and edit files within its
  bounded task contract; on `operations` it stays read-only and must not
  execute tests or external mutations, design tests, diagnose, perform RCA,
  review, decide fixes, or modify product code. The route, not the model
  family, sets these boundaries.
- Use xhigh for deep routes. Never select max automatically; max is a conscious
  one-off user override outside the automatic routing policy.
- Fable is read-only on every automatic route. A user can still choose a
  different model manually for the parent session; that is outside worker
  routing and does not create an automatic authorization bypass.
- A missing provider, unsupported CLI, rejected selector/effort/control, or
  malformed result makes the route unavailable. Never downgrade, retry on a
  cheaper family, or silently use a generic worker.
- The manifest pins the current selectors. When a new model becomes preferred,
  update its one catalog entry and tests; skills and route names stay stable.
- Legacy `tier: Light|Standard|Heavy` frontmatter is non-authoritative workload
  metadata for reference selection only. It never selects a model or effort;
  every actual dispatch uses the stable route named at its inventoried marker.
