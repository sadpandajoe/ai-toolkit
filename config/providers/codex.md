# Codex capability bindings

This provider adapter maps shared capability identifiers to Codex CLI
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax or the declared fallback.

- `planning_boundary`: Codex Plan mode for read-only exploration; for COMPLEX
  work the `aitk-planner` agent drafts the plan through `fresh_subagent` and
  the parent writes `PLAN.md`.
- `fresh_subagent`: Codex custom agents in `$CODEX_HOME/agents/`
  (`aitk-planner`, `aitk-implementer`, `aitk-debugger`, `aitk-tester`), each
  pinning its own model, effort and sandbox as `bin/aitk build` renders them;
  the deep routes run only through `model-run`. The spawn prompt carries the
  full contract per `rules/specialist-handoff.md`.
- Codex delegates only when told: a workflow step that wants a native worker
  says so and names its `agent_type`; a routed lane names its `model-run`
  route instead.
- `parallel_fanout`: several agents in one turn for disjoint units, each under
  its own route and agent controls.
- `isolated_worktree`: create and enter a fresh Git worktree manually.
- `context_reset`: not required; fresh agents are the phase boundary, and a
  session that must end resumes through `start` from the `PROJECT.md` snapshot
  and checkpoint.
- `recurrence`: reinvoke the monitored workflow manually until a stop
  condition, subject to the repository reachability gate.
- `independent_review`: `<toolkit-root>/bin/aitk model-run review --provider
  claude --boundary <marker-id>`. When Claude is unreachable, `bin/aitk review
  plan --unreachable claude` lists the lanes that still run (same contract,
  `--provider codex`) and the `Independent review: same-provider` disclosure.
  Never review inline.
- `routed_subagent`: `<toolkit-root>/bin/aitk model-run <route> --provider
  <codex|claude> --boundary <marker-id>`; it pins the route's model and effort,
  runs Codex targets without user config, hooks or MCP servers, and fails
  closed. Never substitute a generic worker on `MODEL_ROUTE_UNAVAILABLE`.
- `memory_store`: `.ai-toolkit/memory/` at the target repository's top, with
  a `MEMORY.md` index; `.ai-toolkit/` stays in the repository's git exclude
  file like the rest of the local state.

Working style: act without asking when the request and the workflow's
authorization cover the step; size test runs to the change (targeted first,
the full suite only when asked or at a gate that requires it); start with the
work, not a preamble or an upfront plan nobody asked for.
