# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude Code
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: read-only exploration in the parent; for COMPLEX work
  the `aitk-planner` agent drafts the plan through `fresh_subagent` and the
  parent writes `PLAN.md`.
- `fresh_subagent`: the Agent tool with an installed toolkit agent in
  `~/.claude/agents/` (`aitk-planner`, `aitk-implementer`, `aitk-debugger`,
  `aitk-tester`), each pinned to its route's model and effort. The spawn
  prompt carries the full contract per `rules/specialist-handoff.md`; review
  lanes never run as native agents.
- Full-history fork (Claude only): a forked subagent that carries most of the
  live conversation, for a rare side investigation; never a phase boundary.
- `parallel_fanout`: several Agent calls in one turn for disjoint units, each
  under its own route and agent controls.
- `isolated_worktree`: the Agent tool's worktree isolation; a worker worktree
  with no changes is cleaned up automatically, and one with changes comes back
  as a path and branch to merge.
- `context_reset`: not required; fresh agents are the phase boundary and
  auto-compaction protects the parent, so never ask the user to clear.
- `recurrence`: Claude Code's recurring workflow facility with explicit stop
  conditions, subject to the repository reachability gate.
- `independent_review`: `<toolkit-root>/bin/aitk model-run review --provider
  codex --boundary <marker-id>`; the second-family lane is `model-run review
  --provider claude --boundary review.second-family`. When Codex is
  unreachable, `bin/aitk review plan --unreachable codex` lists the lanes that
  still run and the `Independent review: same-provider` disclosure; the
  single-finding verifier runs on `deep-review` (Fable) or the finding stays
  `[minor]` with `Verifier: unavailable — single family`. Never review inline.
- `routed_subagent`: `<toolkit-root>/bin/aitk model-run <route> --provider
  <codex|claude> --boundary <marker-id>` pins the route's model and effort,
  inlines the boundary's contract list and fails closed; never substitute a
  generic worker on `MODEL_ROUTE_UNAVAILABLE`.
- `memory_store`: Claude Code's auto memory directory,
  `~/.claude/projects/<project>/memory/` with its `MEMORY.md` index, or the
  `autoMemoryDirectory` setting when it is set.

Session environment: keep auto-compaction on. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`
(a percentage such as `50`) compacts earlier when the parent grows fast, and
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2` bounds nesting to one worker layer and
one exceptional child.
