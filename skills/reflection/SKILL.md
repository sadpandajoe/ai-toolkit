---
name: reflection
description: Use for recording high-signal workflow observations, reviewing and clustering them, pruning memories, proposing rule or skill changes with eval candidates, and failure postmortems. Do NOT use for ordinary project notes, implementation retrospectives, or product documentation.
---

# Reflection

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Owns the toolkit's learning loop: event-driven observations during real work,
periodic review that clusters them, and human-approved promotion into rules,
skills, and regression evals. There is no always-on observer; only the
high-signal triggers in `references/observations.md` write anything.

## Phases

| Phase | When | Reference |
|---|---|---|
| Record observation | A trigger fired during a workflow | [references/observations.md](references/observations.md) |
| Review observations | `reflect` or `complete-project`; cluster, propose, generate eval candidates | [references/observations.md](references/observations.md) |
| Add or list memories | Capture or inspect memory inventory | [references/memory-basics.md](references/memory-basics.md) |
| Review or prune memories | Accuracy, duplication, staleness | [references/memory-review.md](references/memory-review.md) |
| Propose or promote rule | A cluster or recurring memory justifies a rule or skill change | [references/rule-promotion.md](references/rule-promotion.md) |
| Failure postmortem | A workflow produced a bad outcome | [references/failure-postmortem.md](references/failure-postmortem.md) |

## Notes

- Observations, memories, and evals are local files; rule and skill changes
  need user confirmation and ship with an eval candidate under `evals/`.
- A pattern seen once is a memory; a cluster across projects is a rule
  candidate; a repeated manual workaround is a skill candidate.
- The provider adapter resolves the memory directory; never hard-code it.
