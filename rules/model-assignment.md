# Model and Effort Assignment

`interfaces/model-routing.json` is the only source of truth for volatile model
selectors, provider controls, and effort values. Skills name stable routes;
provider adapters resolve the toolkit/package root, resolve those routes with
`<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, and launch them
with `<toolkit-root>/bin/aitk model-run --boundary <marker-id>`.

| Route | Use | Effort | Codex family | Claude family |
|---|---|---|---|---|
| `implementation` | Normal bounded development | high | Sol | Opus |
| `review` | Bounded plan, code, test, or PR review | high | Sol | Opus |
| `deep-review` | Architecture, security, adversarial, or final cold review | xhigh | Sol | Fable |
| `rca` | Clear, bounded root-cause synthesis | high | Sol | Opus |
| `deep-rca` | Ambiguous, intermittent, historical, or cross-system RCA | xhigh | Sol | Fable |
| `operations` | Read-only evidence reduction and deterministic operational reporting after parent/tool collection | high | Sol | Sonnet |

Rules:

- Keep the main coding session on the user's current Sol-or-newer or Opus
  workhorse at high effort. Routes govern spawned workers, not the already
  active parent session.
- Codex development workers never go below the current Sol family. Claude
  development workers use Opus. Fable is a read-only deep advisor for review
  and RCA, not an automatic implementer.
- Sonnet is read-only operations-only. It must not execute tests or external
  mutations, design tests, diagnose, perform RCA, review, decide fixes, or
  modify product code.
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
