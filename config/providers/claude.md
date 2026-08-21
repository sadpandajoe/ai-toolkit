# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude-native
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: enter and exit Claude's plan-only boundary.
- `fresh_subagent`: launch the assigned stable route through the source-linked `model-run` transport so the fresh process has the pinned selector, effort, permissions, and bounded scope.
- `parallel_fanout`: run independent routed `model-run` processes concurrently; native fan-out schedules them but does not replace their route controls.
- `isolated_worktree`: enter a provider-managed worktree before mutation.
- `context_reset`: use a fresh Claude context after saving the durable checkpoint.
- `recurrence`: use Claude's recurring workflow facility with explicit stop conditions.
- `independent_review`: launch a fresh `review` or `deep-review` process through `model-run`; never reuse the implementing process.
- `routed_subagent`: resolve the toolkit/package root from the installed skill, resolve the declared route with `<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, then run it through `<toolkit-root>/bin/aitk model-run --provider claude --boundary <marker-id>`. This transport sends one exact selector and effort, never supplies `--fallback-model`, and fails if the CLI rejects the request or result contract. Do not use a generic Agent worker when it reports `MODEL_ROUTE_UNAVAILABLE`. See `rules/routed-subagent-integrity.md` for contract-closure and serving-model-identity mechanics.
