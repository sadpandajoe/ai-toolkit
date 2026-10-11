# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude Code
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: read-only exploration in the parent. For COMPLEX work
  the plan itself comes from the `aitk-planner` agent (Fable) via
  `fresh_subagent`; the parent writes `PLAN.md`.
- `fresh_subagent`: the Agent tool with one of the toolkit's installed agents
  in `~/.claude/agents/`: `aitk-planner` (plan-only), `aitk-implementer`
  (edits and runs tests), `aitk-debugger` (evidence-first investigation),
  `aitk-tester` (test authoring). Each agent's frontmatter pins its model
  and effort. Reviewers are not native agents: every review lane, including
  the Claude second family, runs through `model-run`. The spawn prompt carries
  the full contract per `rules/specialist-handoff.md`; the agent returns a
  compact handoff.
- Full-history fork (Claude only): a forked subagent that carries most of the
  live conversation, for a rare side investigation that needs it; never for a
  normal phase boundary, where a fresh worker is the boundary.
- `parallel_fanout`: several Agent calls in one turn for disjoint units; the
  route and agent controls still apply to each.
- `isolated_worktree`: the Agent tool's worktree isolation for slices that may
  commit independently; the parent merges.
- `context_reset`: not required. Fresh agents are the phase boundary and
  auto-compaction protects the parent; never ask the user to clear.
- Session environment: keep auto-compaction on, and set
  `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` lower (for example `80`) when the parent
  grows faster than expected; `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2` bounds
  nesting to the goal skill, one worker layer, and one exceptional child.
- `recurrence`: Claude Code's recurring workflow facility with explicit stop
  conditions, subject to the repository reachability gate.
- `independent_review`: the cross-provider specialist by default. Resolve the
  toolkit root from the installed skill, then run
  `<toolkit-root>/bin/aitk model-run review --provider codex --boundary
  <marker-id>` with the boundary's prompt file; the runner inlines
  `agents/specialists/reviewer.md` and the grading rules. The second-family
  lane is `model-run review --provider claude --boundary
  review.second-family`. If Codex is unreachable, run the independent boundary
  with `--provider claude` and record `Independent review: same-provider`. In that single-provider case the
  second-family lane is skipped and a `review`-route verifier would be Opus
  again, so the single-finding verifier runs on `deep-review` (Fable) or the
  finding stays capped at `[minor]` with `Verifier: unavailable — single
  family` recorded. Never review inline.
- `deep_lenses`: prefer the other provider like any independent judgment. From
  a Claude parent a flagged lens runs through `model-run deep-review --provider
  codex` and spends no Claude quota; the Claude `deep-review` route runs the
  adversarial second vote, the escalation when the Codex lens stayed
  uncertain, and the single-provider verifier fallback.
- `routed_subagent`: `<toolkit-root>/bin/aitk model-route <route> --provider
  <codex|claude> --boundary <marker-id>` then `model-run` with the same
  arguments. The runner pins the route's model and effort, inlines the
  boundary's contract closure, and fails closed; never use a generic worker
  when it reports `MODEL_ROUTE_UNAVAILABLE`.
