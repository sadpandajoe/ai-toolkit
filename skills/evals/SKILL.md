---
name: evals
description: Run one evals/ fixture family through a live model instead of the structural proxy checker — needed when a family's fixtures test a judgment call (skill routing, complexity, size, execution shape) that a keyword/regex checker can only approximate. Do NOT use for structural mode (`bin/aitk evals-run --family <name>`, no dispatch, CI default) or for oracle families (`resume`, `gate_transition`, `safety_effects`, `decomposition`, `review_remediation`, `escalation`) where a pure function already computes the correct answer and a model adds nothing.
---

# Live Evals

`bin/aitk evals-run --family <name> --live` refuses: `aitk/routing_manifest.py`'s `validate_dispatch_boundaries()` only recognizes a boundary marker inside a scanned `skills/**/*.md` file, sitting immediately above the prose that actually performs the dispatch — a bare CLI process is not that, and writing a marker into a file with no such prose next to it would just be decoration aimed at the validator. This skill file is the real thing: whoever runs a live check reads the steps below and carries them out.

## Scope

Only these families have a judgment a live model can check that the structural checker (`aitk/evals_<family>.py`) cannot — each structural checker's own docstring explains what it approximates instead of asking a model:

| Family | Fixture fields | What the structural checker approximates |
|--------|-----------------|---------------------------------------|
| `skill_routing` | `phrase`, `expect_skill` | substring match against each goal skill's frontmatter `description` |
| `complexity` | `scenario`, `expect_complexity` | fixture is well-formed (non-empty scenario, `expect_complexity` is a real enum member) — not whether that's the *correct* classification per `rules/complexity-gate.md` |
| `size` | `scenario`, `expect_size` | same shape-only check as `complexity`, for `expect_size` |
| `execution_shape` | `scenario`, `expect_execution_shape` | same shape-only check as `complexity`, for `expect_execution_shape` |
| `phaseability` | `scenario`, `signal_summary`, `expect_reason`, `expect_execution_shape` | `signal_summary`/`expect_reason` are both present and non-empty — not whether the reasoning they contain is actually sound |

`resume`, `gate_transition`, `safety_effects`, `decomposition`, `review_remediation`, and `escalation` check pure oracle functions in `aitk/checkpoint.py` and friends — a model has no role in their verdicts. Live-checking one of those families would just add cost and nondeterminism for no signal; if asked, refuse and point at structural mode instead.

## Running a family live

1. Load the family's fixtures: `evals/<family>/*.json` (one JSON object per file, per `aitk/evals.py`'s `load_fixtures`).
2. For each fixture, build a prompt from its fields (the phrase or scenario, plus enough of the relevant routing/sizing rules for the model to answer without repo access — e.g. for `skill_routing`, the candidate goal skill names and their frontmatter descriptions; for `complexity`/`size`/`execution_shape`, the relevant decision-tree summary from `skills/planning/references/decompose-work.md`). Ask for exactly the fixture's `expect_*` value (one of the goal-skill names, or one of `TRIVIAL`/`STANDARD`/`COMPLEX`, etc.) and nothing else, so the reply is a single token to compare.

<!-- aitk-model-route:evals.live-check -->
Dispatch each fixture's prompt on the `operations` route (read-only evidence collection: the model answers a classification question, it does not review, decide a fix, or mutate anything): native `operations-worker` when `routed_subagent` is native for the provider, otherwise the plain `operations` route via `model-run` per `config/providers/claude.md`.

3. Compare each response against the fixture's `expect_*` field. Report per-fixture PASS/FAIL plus an `N/M passed` summary, in the same shape `bin/aitk evals-run`'s structural mode already prints.
4. On a FAIL, do not silently adjust the fixture to match the model's answer — a live-mode disagreement is either a real routing bug (fix the skill description or rule) or a bad fixture (fix the fixture), and telling which one it is needs a human or a review pass, not an automatic rewrite.

## Feeding a correction back

When a live run's FAIL turns out to be a real gap (a skill description that doesn't cover a phrasing a user actually used, a sizing rule that's ambiguous on a real scenario), that is the same observation → proposal → fixture loop `rules/rule-maintenance.md`'s Evals signal describes for structural fixtures: record the observation, propose the rule/description fix, and add a fixture (in the family this skill just ran, or a sibling family) that would have caught it structurally next time. The live check is how a gap in the *structural* proxy gets found, not a permanent replacement for it.
