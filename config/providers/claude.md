# Claude capability bindings

This provider adapter maps shared capability identifiers to Claude Code
operations. Shared workflows own behavior and gates; these bindings only select
provider syntax.

- `planning_boundary`: read-only exploration in the parent. For COMPLEX work
  the plan itself comes from the `aitk-planner` agent (Fable) via
  `fresh_subagent`; the parent writes `PLAN.md`.
- `fresh_subagent`: the Agent tool with one of the toolkit's installed agents
  in `~/.claude/agents/`: `aitk-planner` (Fable, plan-only), `aitk-implementer`
  (Sonnet, edits and runs tests), `aitk-debugger` (Sonnet, evidence-first
  investigation), `aitk-tester` (Sonnet, test authoring), `aitk-reviewer`
  (Opus, read-only cold reviewer: the second-family lane on COMPLEX and CORE
  reviews, and the same-provider fallback when Codex is unreachable). The spawn prompt carries
  the full contract per `rules/specialist-handoff.md`; the agent returns a
  compact handoff. Skills whose body is a whole one-shot task may run as forked
  leaf skills (`context: fork`).
- `parallel_fanout`: several Agent calls in one turn for disjoint units; the
  route and agent controls still apply to each.
- `isolated_worktree`: the Agent tool's worktree isolation for slices that may
  commit independently; the parent merges.
- `context_reset`: not required. Fresh agents are the phase boundary,
  auto-compaction protects the parent, `/clear` is optional user hygiene.
  Recommended settings: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`, a lower
  `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` if the parent grows quickly, and the
  `sonnet` model alias for the parent session (not `opusplan`: the planner
  agent, not the parent, runs Fable). Subagents spend the same limit as the
  parent; the Codex review lane does not, so prefer the toolkit's `review-code`
  over general multi-agent review commands when quota is tight.
- `recurrence`: Claude Code's recurring workflow facility with explicit stop
  conditions, subject to the repository reachability gate.
- `independent_review`: the cross-provider specialist by default. Resolve the
  toolkit root from the installed skill, then run
  `<toolkit-root>/bin/aitk model-run review --provider codex --boundary
  <marker-id>` with the boundary's prompt file; the runner inlines
  `agents/specialists/reviewer.md` and the grading rules. If Codex is
  unreachable, run the `aitk-reviewer` agent with the same contract inline and
  record `Independent review: same-provider`. In that single-provider case the
  second-family lane is skipped and a `review`-route verifier would be Opus
  again, so the single-finding verifier runs on `deep-review` (Fable) or the
  finding stays capped at `[minor]` with `Verifier: unavailable — single
  family` recorded. Never review inline.
- `deep_lenses`: prefer the other provider like any independent judgment. From
  a Claude parent a flagged lens runs on Codex Astra through `model-run
  deep-review --provider codex` and spends no Claude quota; Fable runs the
  adversarial second vote, the escalation when Astra stayed uncertain, and the
  single-provider verifier fallback.
- `routed_subagent`: `<toolkit-root>/bin/aitk model-route <route> --provider
  <codex|claude> --boundary <marker-id>` then `model-run` with the same
  arguments. The runner pins one selector and effort, never supplies a fallback
  model, disables ambient skills, inlines the boundary's contract closure, and
  fails closed on a rejected request or result. Provider result envelopes do
  not attest the internal serving model, so backend substitution stays outside
  the toolkit's evidence boundary. Never use a generic worker when it reports
  `MODEL_ROUTE_UNAVAILABLE`.
