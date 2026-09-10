# Model and Effort Assignment

`interfaces/model-routing.json` is the only source of truth for model selectors,
provider controls, and effort values. Skills name stable routes; the runner
resolves them with `<toolkit-root>/bin/aitk model-route --boundary <marker-id>`
and launches specialists with `<toolkit-root>/bin/aitk model-run`.

## Roles

| Role | Claude | Codex | Effort | When |
|---|---|---|---|---|
| Orchestrator (parent session) | Sonnet | Sol | high | Always. Classifies, runs the goal loop, does TRIVIAL and STANDARD work |
| `implementation` | Sonnet | Sol | high | Substantial edits and tests, from an accepted artifact |
| `planning` | Fable | Sol | high | COMPLEX architecture decomposition or a COMPLEX phase plan, read-only |
| `review` | Opus | Sol | high | The one independent code, plan, or PR review |
| `deep-review` | Fable | Astra | xhigh | Adversarial, architecture, or security lens on flagged risk; exceptional escalation |
| `rca` | Opus | Sol | high | Independent RCA validation when the parent's hypothesis is uncertain |
| `deep-rca` | Fable | Astra | xhigh | Competing causes, intermittent or cross-system failures, after `rca` stayed uncertain |
| `operations` | Sonnet | Sol | high | Read-only evidence reduction and deterministic reports |

## Rules

- Prefer the other provider for independent review and validation: a Claude
  parent asks Codex Sol, a Codex parent asks Claude Opus. Same-provider review
  through the toolkit's reviewer agent is the fallback and is disclosed as such.
- Fable plans only COMPLEX work. Sonnet plans STANDARD work inline. Opus stays
  the Claude judgment tier for review, verification, and RCA, so Fable remains
  a distinct escalation rung above them; a COMPLEX plan spends Fable quota
  from a Claude parent.
- Fable and Astra are the read-only deep advisors, one per provider, on the
  deep routes. Neither implements. Deep lenses follow the same other-provider
  preference as review: a Claude parent runs them on Astra first, and Fable is
  the second vote, the escalation when Astra stayed uncertain, and the verifier
  fallback on a single-provider machine.
- `high` is the automatic baseline; `xhigh` is reserved for deep routes and is
  entered only after the standard route stayed materially uncertain. Never
  select `max` automatically.
- A missing provider, rejected selector, or malformed result makes the route
  unavailable. Never downgrade, never retry on a cheaper family, never use a
  generic worker in place of a routed specialist.
- Hotfix and P1 work enters specialists earlier; quality outranks token savings
  there, and safety gates stay strict.
- Promoting a new model changes one catalog entry; route names and skills stay
  stable.
