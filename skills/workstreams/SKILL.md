---
name: workstreams
description: "Use to collect parallel implementation handoffs, track slice status, and merge independent branches in dependency order. Do NOT use for single-threaded work, planning, or spawning the workstreams themselves."
---

# Workstreams

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

This skill owns fan-in after parallel implementation, not the implementation itself.

| Phase | When | Reference |
|-------|------|-----------|
| Sync workstreams | Subagents returned implementation handoffs from isolated branches/worktrees | [references/sync.md](references/sync.md) |

## Boundaries

- Planning decides the slice graph and dependencies.
- `implement-change/` produces per-slice implementation handoffs.
- This skill consumes those handoffs and handles status tracking plus merge sequencing.
