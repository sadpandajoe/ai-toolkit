# Codex capability bindings

This provider adapter maps shared capability identifiers to Codex operations.
Shared workflows own behavior and gates; these bindings only select provider
syntax or the declared fallback.

- `planning_boundary`: use Codex Plan mode for read-only planning.
- `fresh_subagent`: launch the assigned stable route through the source-linked `model-run` transport so the fresh process has the pinned selector, effort, sandbox, and bounded scope.
- `parallel_fanout`: run independent routed `model-run` processes concurrently; collaboration scheduling does not replace their route controls.
- `isolated_worktree`: create and enter a fresh Git worktree manually.
- `context_reset`: save the checkpoint and continue in a fresh Codex session.
- `recurrence`: reinvoke the monitored workflow manually until a stop condition.
- `independent_review`: launch a fresh `review` or `deep-review` process through `model-run`; never reuse the implementing process.
- `routed_subagent`: resolve the toolkit/package root from the installed skill, resolve the declared route with `<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, then run it through `<toolkit-root>/bin/aitk model-run --provider codex --boundary <marker-id>`. This transport sends one exact selector and effort, forbids fallback, and fails if the CLI rejects the request or result contract. Do not use a generic collaboration worker when it reports `MODEL_ROUTE_UNAVAILABLE`. See `rules/routed-subagent-integrity.md` for contract-closure and serving-model-identity mechanics.
