# Migration

## 0.3.0: the Sonnet control plane

Version 0.3.0 keeps the natural-language interface, the durable contracts, and
the safety gates, and replaces what runs underneath them.

### What changes for you

- Run the parent session on the workhorse family: `/model sonnet` on Claude
  Code (not `opusplan`; the planner agent runs Opus, the parent does not), Sol
  on Codex. Opus plans only COMPLEX work; Sol or Opus review independently;
  Fable is a read-only deep advisor.
- Nothing asks you to clear context. Fresh workers are the phase boundary;
  compaction is a safety net; clearing is optional hygiene between tasks.
- Reviews run once, independently, on the other provider when reachable. The
  parent validates each finding before fixing and runs one delta pass after
  substantive fixes. A finding class that survives the delta pass escalates;
  there is no third round.
- Plans are sized to the work. STANDARD work gets a compact inline plan and no
  validation round. COMPLEX work gets an Opus plan and one independent
  validation (`APPROVE / CHANGES_REQUIRED / REPLAN`) with one informed
  revision. Large work is decomposed first and planned one phase at a time.
- You are asked only for a product or design choice, a fact only you hold, a
  blocked environment, or a publish, destructive, or production authorization.

### Vocabulary

| 0.2.0 | 0.3.0 |
|---|---|
| `TRIVIAL / MODERATE / STANDARD` | `TRIVIAL / STANDARD / COMPLEX` (plus size `S/M/L/XL` and shape `SINGLE_PHASE / BATCHED / MULTI_PHASE`) |
| Review Gate `clean / blocked / user decision / skipped / micro-fix` | `## Gate: <name>` with `PASS / RETRY / ESCALATE / RECLASSIFY / USER_DECISION / BLOCKED` |
| Action Gate, stop rules, 8/10 scoring | `rules/gates.md` retry budget and evidence rule |
| Review ensembles, verifier diversity, resolved-state audit | One independent review, validate before fix, delta pass, conditional deep lenses |
| Plan review loop with cold read | `planning/references/validate-plan.md` |
| `checkpoint + context_reset` | Checkpoint, then a fresh worker |

Legacy `MODERATE` in an existing `PROJECT.md` reads as `STANDARD`; the `start`
workflow re-runs the Complexity Gate when a checkpoint predates the routing
snapshot.

### Updating an install

```bash
git pull
./install.sh              # add --with-pgm when needed
bin/aitk doctor --strict
bin/aitk doctor --installed --strict
```

The installer now also links `agents/claude/aitk-*.md` into `~/.claude/agents/`
and `agents/codex/aitk-*.toml` into `$CODEX_HOME/agents/`. Unrelated personal
agents beside them are untouched, and `bin/aitk uninstall` removes only
ledger-owned links. Verify the Codex TOML key set against your Codex CLI
version's custom-agent documentation.

### Removed

`aitk review-ensemble`, `rules/review-gate.md`, `rules/stop-rules.md`,
`rules/scoring.md`, `skills/action-gate/`, the plan-review iteration and
finalize references, and the review ensemble, workflow-review, and adversarial
panel references. Their replacements are covered by `tests/test_conformance.py`
and the eval corpus under `evals/`.

### Contributor changes

- Workflow references are goal loops; compare with `fix-bug.md` and
  `create-feature.md` before inventing a new shape.
- Every dispatch sentence follows an inventoried marker; specialists declare
  their contracts on the boundary. Same-provider workers are the agent roster.
- Add an eval case with every routing, classification, or gate change.
- Run `bin/aitk check` and `git diff --check` before handoff.

## 0.2.0: skills-only interface

Version 0.2.0 removed AI Toolkit's generated Claude slash aliases. Canonical
workflow behavior lives in `skills/workflows/references/`, registered by
`interfaces/workflows.json`, and exposed through the `workflows` Agent Skill.
For every former core `/name [args]` alias, the direct migration is
`$workflows name [args]`; PGM aliases migrate to `$pgm name [args]`. The
installer removes old per-command links only when the ownership ledger records
them as toolkit-owned; personal commands are preserved, and `bin/aitk rollback`
restores the previous transaction.
