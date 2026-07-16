# Codex capability bindings

This provider adapter maps shared capability identifiers to Codex operations.
Shared workflows own behavior and gates; these bindings only select provider
syntax or the declared fallback.

- `planning_boundary`: use Codex Plan mode for read-only planning.
- `fresh_subagent`: spawn a fresh collaboration agent with a bounded task.
- `parallel_fanout`: spawn independent collaboration agents concurrently.
- `isolated_worktree`: create and enter a fresh Git worktree manually.
- `context_reset`: save the checkpoint and continue in a fresh Codex session.
- `recurrence`: reinvoke the monitored workflow manually until a stop condition.
- `independent_review`: spawn a fresh read-only reviewer that did not implement the change.
