# Reasoning Tier Assignment

Reusable workflows name neutral reasoning tiers. Concrete model or effort
controls belong only in provider binding documents.

| Task | Tier | Why |
|---|---|---|
| Deterministic preflight classification | Light | Structured classification with little judgment |
| Mechanical batch worker | Standard | Bounded change with a tight contract |
| Typical implementation worker | Standard | Known coding patterns and contained ownership |
| Meaningful code or plan review | Standard / Heavy | Independence and risk-sensitive judgment |
| Architecture, RCA, conflict, auth, or security work | Heavy | Multi-constraint reasoning and higher blast radius |
| Long-running main coordinator | Orchestrator | Owns ordering, state, user decisions, and synthesis |

Rules:

- Prefer the least expensive tier that can perform the task safely.
- Keep deterministic discovery in tools and files before reasoning.
- Dispatch prompts name the tier, task, exit criteria, and compact handoff.
- Escalate to Heavy for unclear ownership, cross-cutting APIs, migrations,
  security, generated artifacts, or a low-confidence gate.
- Provider adapters map tiers to concrete controls; shared rules never do.
- The orchestrator owns shared-state and branch mutation unless an isolated
  worker receives an explicit, bounded grant.
