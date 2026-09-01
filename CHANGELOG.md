# Changelog

## Unreleased

- **Review ensemble mechanism retired (wave F3).** Deleted
  `skills/review/references/ensemble.md`, the `bin/aitk review-ensemble`
  subcommand, and the roster-resolution/per-lens-floor mechanism behind them
  across `interfaces/model-routing.json`, `aitk/routing_manifest.py`,
  `routing_resolver.py`, `routing_policy.py`, `model_routing.py`,
  `aitk/cli.py`, and `bin/aitk`. `skills/review/**` and
  `skills/workflows/references/review-pr.md` now describe every dispatch
  boundary as one reviewer pass over a fixed lens/contract set (the
  triggered set from `classify-diff.md`), migrated onto `rules/gates.md`'s
  six-state contract (PASS/RETRY/ESCALATE/USER_DECISION/BLOCKED) in place of
  numeric `/10` scoring and the old MODERATE/STANDARD tier names
  (MODERATE→STANDARD, STANDARD→COMPLEX).
- **Native worker roster completed.** With `agents/claude/deep-rca-worker.md`
  and `operations-worker.md` (wave F1+F2) and the ensemble retirement above,
  every route declared in `interfaces/model-routing.json` — `deep-rca`,
  `deep-review`, `implementation`, `operations`, `planning`, `rca`, `review`
  — now dispatches through a native `agents/claude/*.md` worker.
  `interfaces/providers.json` declares Claude's `routed_subagent` binding
  `native` with no fallback; the source-linked `model-route`/`model-run`
  transport remains live only for the three Codex specialists
  (`agents/codex/{rca,plan-validator,reviewer}.md`), which have no native
  roster of their own.

## 0.3.0 — 2026-08-27

v2 refactor closing the gaps between this toolkit and its spec's 8-wave
roadmap (§15). Executed as four internal waves (A–D); see `PLAN.md` for the
full slice-by-slice record, including deferrals.

- **State foundation (roadmap W1).** `aitk project-state` now reads and
  merges PROJECT.md's YAML frontmatter into the routing snapshot — `size`,
  `execution_shape`, `phase_*`, `verification_status`, `reasoning_attempts` —
  and the checkpoint block persists accepted-artifact/evidence references
  (`accepted_rca`, `accepted_decomposition`, `accepted_phase_plan`,
  `evidence[]`, `reclassifications[]`) so a snapshot alone suffices to resume.
- **Verification loop (roadmap W2).** `skills/verification-loop` was
  rewritten to the six-state contract — PASS / RETRY / ESCALATE /
  RECLASSIFY / USER_DECISION / BLOCKED — replacing numeric 8/10 convergence
  and "same reason twice" iteration counting with a reasoning-retry budget
  (`aitk/gates.py`'s `decide_failure(kind=mechanical|reasoning)`): mechanical
  repairs never consume retry budget, a second reasoning failure escalates
  autonomously (effort → model → XHigh) before ever surfacing to the user.
  Codex specialist contracts moved to verdict vocabulary (APPROVE / CHANGES
  REQUIRED / REPLAN for plan-validator; severity-tagged findings, no `/10`,
  for the reviewer).
- **Ten goal workflows (roadmap W4–W6).** All of `skills/goals/{fix-bug,
  create-feature, code-review, fix-ci, cherry-pick, address-feedback,
  test-pr, watch-pr, refactor, release-prep}` now chain the shared
  verification loop and classify size/execution-shape instead of running a
  private gate loop. `watch-pr`, `refactor`, and `release-prep` are new;
  `release-prep`'s publish step is a separate protected-effect authorization
  gate, not folded into the review loop. Goal skills dispatch a single SOL
  review (with a delta pass on trigger) instead of the old generic review
  route. `rules/{model-assignment,complexity-gate,context-management,
  universal,input-detection,resource-management,code-review}.md` were
  rewritten to match (Sonnet default / Opus COMPLEX-planning-only / SOL
  RCA-validation-review, size+shape derivation in place of the 8/10 idiom,
  workers as the phase-level context reset).
- **Learning loop and eval corpus (roadmap W7).** A new `observation`
  telemetry event (`user-correction` / `skill-misroute` / `reclassify` /
  `gate-repeat` / `plan-invalidated` / `manual-workaround`) is emitted only
  from existing gate/reclassify/workflow-summary steps — no always-on
  observer. `skills/reflection` clusters observations by skill and kind and
  writes proposals; every ACTIONED skill-misroute or gate-repeat produces a
  candidate `evals/` fixture. `model`/`workflow-summary` telemetry events
  gained token accounting (`input_tokens`, `output_tokens`, `cache_tokens`,
  `total_tokens`, `premium_tokens`). Added the eval-harness runner and the
  first eval fixture family, `evals/skill_routing/`.
- **v1 deletion and native workers (roadmap W8).** Deleted `skills/
  {workstreams,action-gate,plan-review}` and `planning/references/
  iterate-review.md`, repointing their citers onto native Claude subagents,
  `rules/gates.md`, and `agents/codex/plan-validator.md`. `skills/workflows`
  is now a pure compatibility shim — every `interfaces/workflows.json` entry
  names a goal skill or a utility reference. Six of the nine roster roles
  (`planner`, `implementation-worker`, `debug-worker`, `test-worker`,
  `review-worker`, `deep-review-worker`) now dispatch as native
  `agents/claude/*.md` Claude Code subagents, needing no source-linked
  transport.
- **Deferred, by design, not by omission.** `rules/{scoring,stop-rules,
  review-gate}.md` remain authoritative for the plan-domain reviewers and for
  `skills/planning`'s and `skills/testing`'s review helpers —
  `rules/gates.md`'s six-state contract supersedes them only for its own
  listed migrated citers. `review/references/ensemble.md` and `bin/aitk
  review-ensemble` remain live: four orchestration references still dispatch
  through the ensemble roster, and lifting that deferral is unscoped
  follow-up work. Three Claude boundaries — `deep-rca`, `operations`, and the
  review-ensemble lanes — still use the source-linked `model-run` transport
  because no native worker file exists for them yet.
- Docs: `docs/ARCHITECTURE.md` rewritten to the target repository shape;
  `docs/MIGRATION.md` gained a v1→v2 section; this entry.

## 0.2.0 — 2026-07-21

- Added canonical, fail-closed model and effort routes for Codex and Claude
  workers, including high-effort workhorse defaults, xhigh deep review/RCA,
  Sonnet operations-only constraints, and future-proof selector promotion.
- Added `aitk model-route` and `aitk model-run`, dispatch-boundary validation,
  provider CLI preflight, structured worker results, and no-downgrade behavior.
- Removed generated Claude slash-command aliases in favor of natural-language
  routing and the public `$workflows` and `$pgm` Agent Skills.
- Preserved upgrade-safe cleanup of toolkit-owned legacy command links while
  leaving unrelated personal commands untouched.
- Made CI portable across macOS path aliases and Python 3.11–3.14, enabled PEP
  517 build isolation, and eliminated duplicate push runs for PR branches.

## 0.1.0 — 2026-07-15

- Moved all daily workflow procedures from commands into a canonical provider-neutral workflow skill.
- Added the deterministic `aitk` build, route, list, doctor, and conformance interfaces.
- Added safe idempotent Claude/Codex guidance and skill installation while preserving unrelated user configuration.
- Added a validated Codex plugin manifest, Agent Skills metadata, and provider-neutral lifecycle hooks.
- Added routing, safety, installer, build, portability, resume, and behavioral contract tests.
- Standardized local metrics under `.ai-toolkit/metrics.jsonl` with legacy-read migration.
- Removed personal paths, unsafe secret diagnostics, `eval` retries, destructive RBAC defaults, and provider primitives from shared workflows.
- Migrated the optional PGM reports to a manifest-backed Agent Skill with generated aliases, opt-in routing, and reversible installation.
- Added SHA-pinned CI that initially ran the same complete conformance gate as
  local development on Python 3.11 and 3.14; the later expansion to Python
  3.11–3.14 is recorded below.
- Added strict v2 workflow contracts and a deterministic checkpoint CLI with
  phase, generation, reservation, reconciliation, and replay validation.
- Added a mode-0600 ownership ledger with atomic install/upgrade/uninstall,
  one-level rollback, moved-checkout migration, hostile-ledger refusal, and
  crash-boundary restoration.
- Classified every skill as public router, public direct, or internal support;
  source-linked installs expose only the public surface.
- Added PGM configuration preflight and timestamp-aware promotional pricing;
  missing/invalid historical timestamps remain unpriced.
- Expanded CI to the macOS/Ubuntu and Python 3.11-3.14 matrix with untracked
  generated-adapter rejection and isolated wheel smoke testing.
