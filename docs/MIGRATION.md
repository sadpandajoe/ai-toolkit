# 0.2.0 Skills-Only Migration

Version 0.2.0 removes AI Toolkit's generated Claude slash aliases. Canonical
workflow behavior remains in `skills/workflows/references/`, registered by
`interfaces/workflows.json`, and exposed through the `workflows` Agent Skill.

## Invocation changes

Use a natural-language request or explicitly invoke the router:

```text
Fix this bug: pagination skips rows after an update
$workflows fix-bug "pagination skips rows after an update"

Review my local changes
$workflows review-code

Create a current program status report
$pgm create-status-report
```

For every former core `/name [args]` alias, the direct migration is
`$workflows name [args]`. Optional PGM aliases migrate to `$pgm name [args]`.
Claude's built-in commands, including `/review`, are not owned or changed by AI
Toolkit.

## Updating a source-linked install

```bash
git pull
./install.sh              # add --with-pgm when needed
bin/aitk doctor --strict
bin/aitk doctor --installed --strict
```

The installer removes old per-command links only when the ownership ledger
records them as toolkit-owned. It also migrates the old whole-directory
`.claude/commands` link when it points at this toolkit's legacy generated
output. Unrelated personal commands and directories are preserved. Existing
ignored `build/commands/` output may remain as one-level rollback material; it
is not installed or treated as a public interface in 0.2.0.

Use `bin/aitk uninstall` to remove matching owned artifacts or `bin/aitk
rollback` to restore the last exact install/upgrade/uninstall transaction.
Manual deletion loses recovery evidence and is not the supported lifecycle.

## Contributor changes

- Add or edit canonical workflow references under
  `skills/workflows/references/` and register routing metadata in
  `interfaces/workflows.json`.
- Keep shared `SKILL.md` frontmatter provider-neutral. Put Codex invocation
  policy in `skills/<name>/agents/openai.yaml` and provider-specific behavior in
  adapters.
- Run `bin/aitk build --with-pgm` to validate core and optional manifests and
  regenerate path-resolved provider guidance.
- Run `bin/aitk check` and `git diff --check` before handoff.

PGM remains source-linked-only in 0.2.0; the Codex plugin distribution contains
the core `skills/` tree and does not advertise `$pgm`.

Existing hand-written continuation blocks should be reinitialized with
`bin/aitk checkpoint init --workflow <name> --replace`. Normal init is a no-op
when the same valid workflow already owns the artifact, and replacement refuses
while any effect remains pending.

## 0.3.0: v1 → v2 migration

Version 0.3.0 moves workflow behavior into `skills/goals/` and shrinks
`skills/workflows/` to a pure compatibility shim. See `docs/ARCHITECTURE.md`
for the target shape and `PLAN.md` for the wave-by-wave record this section
summarizes.

### Invocation

Natural-language requests now route directly to a goal skill
(`skills/goals/fix-bug`, `create-feature`, `code-review`, `fix-ci`,
`cherry-pick`, `address-feedback`, `test-pr`, `watch-pr`, `refactor`,
`release-prep`).
`$workflows name [args]` still works — every entry in
`interfaces/workflows.json` names either a goal skill or a utility reference —
but it is no longer where workflow logic lives, so treat it as a stable alias,
not the canonical location to edit.

`address-feedback` is this repo's name for what the v2 spec calls
`pr-feedback`; keeping that name is still an open decision (see PLAN.md's
"Open decisions for the user"), not a completed rename.

### Vocabulary: v1 complexity tiers → v2

v1's three-tier complexity vocabulary does not carry over 1:1 — the same word
means a different tier in v1 and v2, so a reader following an old note must
remap it, not skim it:

| v1 term | v2 term |
|---|---|
| `TRIVIAL` | `TRIVIAL` |
| `MODERATE` | `STANDARD` |
| `STANDARD` | `COMPLEX` |

`NON-TRIVIAL` and any `/10` numeric review score are v1-only; the six-state
gate contract (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED) replaces
scored thresholds for every migrated goal-skill path. `rules/{scoring,
stop-rules,review-gate}.md` still use the old scored-threshold vocabulary, but
only for the plan-domain reviewers named in "Kept, not deleted" below — that
is a recorded deferral, not a second live scoring system for goal workflows.
`aitk/routing.py`'s `_LEGACY_COMPLEXITY_MAP` performs this same remap
mechanically for any `routing-state` block written under the old vocabulary.

### Deleted

- `skills/workstreams`, `skills/action-gate`, `skills/plan-review` — repointed
  to native Claude subagents, `rules/gates.md`, and
  `agents/codex/plan-validator.md` respectively. `planning/references/
  iterate-review.md` was deleted alongside them.

### Kept, not deleted (deliberate deferral)

- `rules/{scoring,stop-rules,review-gate}.md` remain authoritative for the
  plan-domain reviewers (`skills/review/references/{architecture,frontend,
  backend}.md`, `agents/codex/plan-validator.md`) and for `skills/planning`'s
  and `skills/testing`'s review helpers. `rules/gates.md`'s six-state contract
  (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED) supersedes them only
  for its own listed migrated citers.
- `review/references/ensemble.md` and `bin/aitk review-ensemble` remain live.
  Four orchestration references still dispatch through the ensemble roster in
  live steps, and sol-review/delta-review's retirement gate isn't fully met
  yet. Lifting this deferral is unscoped follow-up work, not part of this
  migration.

### Model transport

Six of the nine roster roles (`planner`, `implementation-worker`,
`debug-worker`, `test-worker`, `review-worker`, `deep-review-worker`) dispatch
natively as Claude Code subagents under `agents/claude/`, with no
source-linked transport. `bin/aitk model-route` / `model-run` remain the
transport for the three Codex specialists (`agents/codex/{rca,plan-validator,
reviewer}.md`) and for three Claude boundaries that have no native worker file
yet: `deep-rca`, `operations`, and the review-ensemble lanes. The Claude-side
`model-run` closure code cannot be removed until those three either go native
or are deleted.

**Ratified 2026-08-27 (user, via AskUserQuestion): option (b), "go native."**
The spec's original text names Codex SOL as the independent verifier for
`review`/`deep-review` unconditionally. This repo instead runs those two
boundaries as native Claude subagents when the active provider is Claude:
`agents/claude/review-worker.md` (the `review` route, Opus) and
`agents/claude/deep-review-worker.md` (the `deep-review` route, Fable) — two
files, not one, because `interfaces/model-routing.json` pins the two routes
to different models and a single frontmatter `model:` field cannot carry
both. Codex SOL (`agents/codex/reviewer.md`) remains the independent verifier
only when the active provider is Codex, which has no native worker roster.
`config/providers/claude.md`'s `routed_subagent` entry and `independent_review`
entry record the binding; `rules/model-assignment.md` and
`docs/ARCHITECTURE.md`'s "Model workers" section carry the same decision.

### Docs and telemetry

`docs/TELEMETRY.md` already documented `observation` events and the
`input_tokens`/`output_tokens`/`cache_tokens`/`total_tokens`/`premium_tokens`
fields before this migration; no v1→v2 change was needed there.
