# Evals

Tests protect invariants and deterministic state transitions; evals protect
model judgment. Neither exists to preserve an architecture the toolkit no
longer wants.

Each family is a JSONL file of cases with `id`, `mode`, `input`, `expected`,
and `source` (`plan`, `migration`, or `observation` when it came from the
reflection queue).

| Family | Protects |
|---|---|
| `skill_routing/` | Natural-language request → workflow, remediation on or off |
| `complexity/` | TRIVIAL / STANDARD / COMPLEX, size, execution shape, hard overrides |
| `gates/` | RETRY versus ESCALATE, evidence rule, safety gates, delta-review policy |
| `planning/` | Single-phase versus decomposition, just-in-time phase plans, bounded validation |
| `workflows/` | End-to-end behavior on representative tasks, resume from the snapshot |

## Running

- `mode: deterministic` cases run in `tests/test_evals.py` through the
  toolkit's own code (`aitk route`, `aitk.project_state`), so they are part of
  `bin/aitk check`.
- `mode: judgment` cases are prompts for a model session. Run them through the
  provider CLI in a scratch repository, compare the workflow's Complexity Gate,
  gate blocks, and metrics event to `expected`, and record misses as
  observations. They are not run in CI.

Track the false-COMPLEX rate (wasted premium calls) and the false-STANDARD rate
(rabbit holes) from these results. Add a case whenever an observation shows a
misroute, a reclassification, or a repeated gate failure.
