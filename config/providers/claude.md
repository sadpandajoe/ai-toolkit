# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude-native
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: enter and exit Claude's plan-only boundary.
- `fresh_subagent`: every Claude-side dispatch boundary now has a native
  `agents/claude/` worker (see `routed_subagent` below for the roster), so
  native Task-tool dispatch is always the fresh, bounded process — a
  separate `model-run` call is never needed on the Claude side. This
  capability's own binding in `interfaces/providers.json` stays `fallback`/
  `source_linked_model_run` regardless, for the same schema-independence
  reason `independent_review`'s does below; that declared fallback has no
  live Claude-side consumer, but the binding stays as written because
  `fresh_subagent` and `routed_subagent` are validated as independent
  capabilities and one going fully native does not change the other's
  schema requirement.
- `parallel_fanout`: run independent routed `model-run` processes concurrently; native fan-out schedules them but does not replace their route controls.
- `isolated_worktree`: enter a provider-managed worktree before mutation.
- `context_reset`: use a fresh Claude context after saving the durable checkpoint. Not required for conformance (`interfaces/providers.json`) — `rules/context-management.md`'s "No Explicit-Reset Dependency" makes worker isolation primary and auto-compact the backstop; `CLAUDE_CODE_AUTO_COMPACT_WINDOW` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` are the recommended, non-default env vars that reinforce those two mechanisms (see that rule file's "Recommended Provider Settings").
- `recurrence`: use Claude's recurring workflow facility with explicit stop conditions.
- `independent_review`: `routed_subagent`'s native dispatch (see below)
  already supplies a fresh, non-implementing process for `review`/
  `deep-review`; this capability's own binding stays
  `fallback`/`source_linked_model_run` regardless, since `independent_review`
  and `routed_subagent` are validated as fully independent capabilities
  (`aitk/routing_manifest.py`'s `validate_route_bindings`) — going native on
  one does not change the other's binding or its schema requirement.
- `routed_subagent`: for the eight roster roles with a native worker file
  under `agents/claude/` — `implementation-worker` (the `implementation`
  route), `debug-worker` (the `rca` route), `deep-rca-worker` (the
  `deep-rca` route), `test-worker` (the `testing.test-authoring` boundary),
  `planner` (the `COMPLEX` complexity-gate trigger), `review-worker` (the
  `review` route), `deep-review-worker` (the `deep-review` route), and
  `operations-worker` (the `operations` route) — dispatch by name through
  Claude Code's native Task-tool subagent mechanism; each worker file's own
  frontmatter (`tools`, `model`) carries the route's permission/model
  restrictions, so no separate transport call is needed. `review`/
  `deep-review` and `rca`/`deep-rca` are each two worker files, not one,
  because `interfaces/model-routing.json` pins their plain and deep tiers to
  different models (Opus/Fable and Sonnet/Fable respectively) and a single
  frontmatter `model:` field cannot carry both. Every route that appears in
  `interfaces/model-routing.json` now has a native worker in this roster —
  `deep-rca`, `deep-review`, `implementation`, `operations`, `planning`,
  `rca`, and `review` — so **no Claude-side dispatch boundary remains on the
  old `model-route`/`model-run` shim**; `interfaces/providers.json` declares
  `routed_subagent` as `native` with no fallback for this reason. The old
  transport (resolve the toolkit/package root from the installed skill,
  resolve the declared route with `<toolkit-root>/bin/aitk model-route
  --boundary <marker-id>`, then run it through `<toolkit-root>/bin/aitk
  model-run --provider claude --boundary <marker-id>`) is documented here
  only as history: do not use a generic Agent worker when it reports
  `MODEL_ROUTE_UNAVAILABLE` — dispatch the named native worker instead.
  `aitk/routing_transport.py` and `aitk/routing_closure.py` are not dead
  code, though: Codex's specialists (`agents/codex/rca.md`,
  `plan-validator.md`, `reviewer.md`) still resolve routes and run through
  `model-run` on that path, so it stays live for the Codex provider adapter
  even though no Claude boundary calls it any more.
