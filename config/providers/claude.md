# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude-native
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: enter and exit Claude's plan-only boundary.
- `fresh_subagent`: launch a new Task worker with only the assigned scope.
- `parallel_fanout`: launch independent Task workers in one parallel group.
- `isolated_worktree`: enter a provider-managed worktree before mutation.
- `context_reset`: use a fresh Claude context after saving the durable checkpoint.
- `recurrence`: use Claude's recurring workflow facility with explicit stop conditions.
- `independent_review`: launch a fresh read-only reviewer that did not implement the change.
