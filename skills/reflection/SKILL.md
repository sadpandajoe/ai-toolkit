---
name: reflection
description: Use for memory review, pruning, rule promotion, and workflow failure postmortems. Do NOT use for ordinary project notes, implementation retrospectives, or product documentation.
---

# Reflection

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

This skill owns memory management and rule-promotion workflows used by `reflect`.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Add/List memories | Capture a memory or inspect memory inventory | [references/memory-basics.md](references/memory-basics.md) |
| Review/Prune memories | Assess accuracy, duplication, staleness, and deletion candidates | [references/memory-review.md](references/memory-review.md) |
| Propose/Promote rule | Convert recurring patterns into rule changes | [references/rule-promotion.md](references/rule-promotion.md) |
| Failure postmortem | Record a structured failure memory with prevention guidance | [references/failure-postmortem.md](references/failure-postmortem.md) |

## Notes

- The provider adapter resolves its configured memory directory. Do not hard-code one provider's storage path in the shared workflow.
- Memory files use YAML frontmatter plus structured body.
- Rule changes require confirmation.
- A pattern seen once is a memory; a pattern seen across projects can become a rule candidate.
