# Codex capability bindings

This provider adapter maps shared capability identifiers to Codex CLI
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax or the declared fallback.

- `planning_boundary`: Codex Plan mode for read-only exploration. For COMPLEX
  work the plan comes from the `aitk-planner` agent via `fresh_subagent`; the
  parent writes `PLAN.md`.
- `fresh_subagent`: Codex custom agents installed in `$CODEX_HOME/agents/`:
  `aitk-planner` (read-only), `aitk-implementer`, `aitk-debugger`,
  `aitk-tester`. They inherit the parent's Sol model and pin their own effort
  and sandbox; the deep routes (`deep-review`, `deep-rca`) never run as agents
  and go through `model-run`, which pins Astra at `xhigh` (Codex CLI 0.153.0 or
  newer). The spawn prompt carries the full contract per
  `rules/specialist-handoff.md`; the agent returns a compact handoff.
- `parallel_fanout`: spawn several agents in one turn for disjoint units; the
  route and agent controls still apply to each.
- `isolated_worktree`: create and enter a fresh Git worktree manually.
- `context_reset`: not required. Fresh agents are the phase boundary; when a
  session must end, `start` resumes from the `PROJECT.md` snapshot and
  checkpoint in a new session.
- `recurrence`: reinvoke the monitored workflow manually until a stop
  condition, subject to the repository reachability gate.
- `independent_review`: the cross-provider specialist by default. Resolve the
  toolkit root from the installed skill, then run
  `<toolkit-root>/bin/aitk model-run review --provider claude --boundary
  <marker-id>` with the boundary's prompt file; the runner inlines
  `agents/specialists/reviewer.md` and the grading rules. If Claude is
  unreachable, run the same contract through a fresh Codex agent on `review`
  via `model-run --provider codex` and record `Independent review:
  same-provider`. Never review inline.
- `routed_subagent`: `<toolkit-root>/bin/aitk model-route <route> --provider
  <codex|claude> --boundary <marker-id>` then `model-run` with the same
  arguments. For Codex targets the runner launches from a sanitized temporary
  project root, exposes the target only as a scoped `--add-dir`, disables user
  config, hooks, MCP servers, exec-policy rules, and project-document
  discovery, pins one selector and effort, forbids fallback, and fails closed on
  a rejected request or result. Codex JSONL does not attest the internal
  serving model. Never use a generic worker when it reports
  `MODEL_ROUTE_UNAVAILABLE`.
