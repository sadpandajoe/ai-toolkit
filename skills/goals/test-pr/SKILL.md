---
name: test-pr
description: Use when you want to manually verify a PR's user-visible behavior in a running local or staging app — browser scenario execution with screenshot/video evidence, optional posting. Do NOT use for automated pytest/jest test authoring (skills/testing), code review of the diff itself (skills/goals/code-review), or full curated test-plan runs (run-test-plan workflow).
---

# Test PR

## Before Starting

Read `rules/gates.md` (six-state gate contract) and the `test-pr` entry in
`interfaces/contracts.json` (durable runtime: effect `external_effect`,
authorization mode `explicit` with gates `production-refusal`/
`destructive-confirmation`/`verification`, phases
prepare→execute→verify→report, resumable via `PROJECT.md`) before
continuing. This skill is the v2 goal-skill entry point for manual PR
testing; it delegates the actual procedure to four existing references
under `skills/qa/references/test-pr/` rather than reimplementing them —
read all four before continuing, since this skill's steps assume their
Inputs/Procedure/Output shape:

- `setup.md` — resolve PR, checkout, app URL, auth.
- `scenarios.md` — impact assessment (CORE/STANDARD/PERIPHERAL, via
  `skills/qa/references/assess-impact.md`) and scenario derivation.
- `execute.md` — run browser scenarios with evidence capture.
- `report.md` — report or post results.

## Scope

**In scope:** manually verifying a PR's user-visible behavior in a running
app — resolving the target, assessing impact, deriving and executing
scenarios, capturing evidence, and reporting or posting results.

**Out of scope:** writing or updating automated tests — that's
`skills/testing`'s own `test-worker` role, unrelated to this skill —
reviewing the diff itself (`skills/goals/code-review`), and full curated
multi-scenario validation runs, which stay `run-test-plan`'s own scope.

## Steps

1. Resolve the target PR, optional `--checkout`, the app URL (or `--url` for
   staging), and auth per `setup.md`. Stop if the app URL cannot be
   resolved, and stop outright on a production URL — this is a hard gate,
   not a tier-dependent one.
2. Follow `scenarios.md`'s procedure: assess impact via `assess-impact.md`,
   classify CORE/STANDARD/PERIPHERAL, and derive the scenario list — a
   1-2 scenario smoke is acceptable for a very small or mechanical PR when
   the impact assessment supports it. Do not re-derive a separate
   complexity tier here; this classification is the only one this skill
   needs.
3. Follow `execute.md`'s procedure: run scenarios sequentially (never
   parallelize browser evidence gathering), record by default (skip only
   with `--no-record`), and capture screenshot/video evidence per scenario.
4. Follow `report.md`'s procedure: assemble the per-scenario results table
   and evidence paths. Stop before posting unless `--post` was passed and
   evidence paths are available.
5. Write the PROJECT.md discipline this workflow requires before any
   checkpoint + context_reset, and before the chat summary on every run —
   not just STANDARD/expensive ones:
   - After scenario selection (STANDARD/expensive runs only): `## Test-PR
     Scenarios`.
   - After execution (STANDARD/expensive runs only): `## Test-PR Results`.
   - Every run, at minimum: a single `## Test-PR Results — PR #[number]`
     entry at completion (see `test-pr.md`'s TRIVIAL/MODERATE template).
   - After posting: `## Test-PR Posted`.

   Do not emit the chat summary until the `## PROJECT.md Updated —
   Test-PR Results` confirmation block has been emitted — this ordering is
   a hard requirement, not a suggestion.
6. Emit the terminal `## Test-PR Complete` summary (PR identity, branch,
   app URL, impact tier, results table, evidence paths, next steps).

## Output

The `## PROJECT.md Updated — Test-PR Results` confirmation followed by the
terminal `## Test-PR Complete` summary — or an earlier stop (unresolved app
URL, production URL, or a posting gate not yet satisfied) with the reason.

## Notes

- This skill is dual-run alongside
  `skills/workflows/references/test-pr.md` today; nothing dispatches
  "test this PR"/"manually test pr" requests here yet. The dual-run router
  pointer that makes this skill a live dispatch target lands in a later
  commit. Reading and testing it does not change live behavior.
- This command does not modify code or file bugs — mirrors
  `test-pr.md`'s own Notes.
- Declares no dispatch boundaries of its own — `qa.fresh-validation`,
  already registered in `interfaces/model-routing.json`, is
  `skills/qa/SKILL.md`'s own boundary and covers every optional model
  dispatch this skill's procedure might reach; see that skill's own
  Invocation Patterns section for the marked dispatch line.
