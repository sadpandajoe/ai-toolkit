# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude-native
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: enter and exit Claude's plan-only boundary.
- `fresh_subagent`: launch the assigned stable route through the source-linked `model-run` transport so the fresh process has the pinned selector, effort, permissions, and bounded scope.
- `parallel_fanout`: run independent routed `model-run` processes concurrently; native fan-out schedules them but does not replace their route controls.
- `isolated_worktree`: enter a provider-managed worktree before mutation.
- `context_reset`: use a fresh Claude context after saving the durable checkpoint. Not required for conformance (`interfaces/providers.json`) — `rules/context-management.md`'s "No Explicit-Reset Dependency" makes worker isolation primary and auto-compact the backstop; `CLAUDE_CODE_AUTO_COMPACT_WINDOW` and `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` are the recommended, non-default env vars that reinforce those two mechanisms (see that rule file's "Recommended Provider Settings").
- `recurrence`: use Claude's recurring workflow facility with explicit stop conditions.
- `independent_review`: `routed_subagent`'s dispatch (native worker or shim,
  per boundary — see below) already supplies a fresh, non-implementing
  process for `review`/`deep-review`; this capability's own binding stays
  `fallback`/`source_linked_model_run` regardless, since `independent_review`
  and `routed_subagent` are validated as fully independent capabilities
  (`aitk/routing_manifest.py`'s `validate_route_bindings`) — going native on
  one does not change the other's binding or its schema requirement.
- `routed_subagent`: for the six roster roles with a native worker file
  under `agents/claude/` — `implementation-worker` (the `implementation`
  route), `debug-worker` (the `rca` route), `test-worker` (the
  `testing.test-authoring` boundary), `planner` (the `COMPLEX`
  complexity-gate trigger), `review-worker` (the `review` route), and
  `deep-review-worker` (the `deep-review` route) — dispatch by name through
  Claude Code's native Task-tool subagent mechanism; each worker file's own
  frontmatter (`tools`, `model`) carries the route's permission/model
  restrictions, so no separate transport call is needed. `review` and
  `deep-review` are two worker files, not one, because
  `interfaces/model-routing.json` pins them to different models (Opus and
  Fable respectively) and a single frontmatter `model:` field cannot carry
  both. For every other routed dispatch boundary — `deep-rca`,
  `operations`, and the review-ensemble lanes — no native worker file exists
  yet, so this capability's old transport remains the documented, explicit
  shim: resolve the toolkit/package root from the installed skill, resolve
  the declared route with `<toolkit-root>/bin/aitk model-route --boundary
  <marker-id>`, then run it through `<toolkit-root>/bin/aitk model-run --provider claude --boundary <marker-id>`. The runner derives and inlines
  the boundary's validated transitive contract closure because safe mode
  disables ambient skills; per-file SHA-256 labels are diagnostic content
  identifiers, not an independently trusted integrity gate. This transport
  sends one exact selector and effort, never supplies `--fallback-model`, and
  fails if the CLI rejects the request or result contract. The supported
  success envelope does not attest the provider's internal serving-model
  identity, so backend substitution remains outside the toolkit's evidence
  boundary. Do not use a generic Agent worker when it reports
  `MODEL_ROUTE_UNAVAILABLE`. This shim stays live for the three boundaries
  that still lack a native worker file — `deep-rca`, `operations`, and the
  review-ensemble lanes — independent of the six now-native roles above,
  which already dispatch without it. Removal condition, boundary by
  boundary: either a native `agents/claude/` worker file is added for that
  boundary (same pattern as the six native roles), or the boundary itself is
  deleted (the review-ensemble lanes go with `review/references/ensemble.md`
  and `bin/aitk review-ensemble` in Wave D2). Until then,
  `aitk/routing_transport.py`/`routing_closure.py` and the Claude-side
  `model-run` path stay — D4's "remove Claude-side closure code" is not yet
  executable as stated; see PLAN.md's D4 note.
