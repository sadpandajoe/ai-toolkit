# Changelog

## 0.3.0 — 2026-09-05

- Gate runtime: only `RETRY` charges the attempt budget; `--editorial` records
  a wording-only fix without charging; `USER_DECISION` and `BLOCKED` never
  charge; `ESCALATE` climbs a per-unit ladder (three steps, then
  `USER_DECISION`) and resets the budget for the next owner; `RECLASSIFY`
  resets counters. Snapshots gain an `escalations` map; older snapshots read
  as empty. The `## Routing Snapshot` heading in `PROJECT_TEMPLATE.md` is
  reused instead of duplicated.
- Verification strength (`STRONG` / `PARTIAL` / `WEAK`) maps to gate outcomes
  in `rules/gates.md`; auto-commit and push in `fix-bug`, `fix-ci`, and
  `watch-pr` require `STRONG`; `--gate-strict` removes the `WEAK` downstream
  carve-out.
- COMPLEX and CORE-impact reviews run a second cold lane on the other model
  family (`review.second-family`, `review.pr-second-family`) merged by
  convergence; elsewhere single-source `[major]` findings are verified by a
  fresh lane on the other model family (`review.verify-major`,
  `agents/specialists/finding-verifier.md`) before they block; security-sensitive, `--deep`, and adversarial reviews are
  `BLOCKED (degraded)` without a cross-provider lane unless `--allow-degraded`.
- Plan validation cases are one list: every decomposition, every COMPLEX plan,
  and a STANDARD plan at `LOW` classification confidence.
- The independent reviewer contract inlines the tests, frontend, and backend
  checklists; the plan validator inlines the implementation and test-plan
  checklists; the unused plan lens floor is gone. Batch PR reviews report
  deep-quality among deferred lenses.
- Phase model: per-unit reviews measure a phase base and the branch base is
  reserved for a new integrated review that gates `## Feature Complete` and
  `## Bug Fix Complete` on MULTI_PHASE and BATCHED work; `## Phase Complete`
  carries a roadmap check whose `no` is `RECLASSIFY` plus one decomposition
  revalidation; one commit or PR per phase is the default delivery with a
  recorded single-PR opt-out; the phase-size guard has numbers (10 files, 500
  lines) and the horizontal-layer and one-sitting checks; size L leans
  MULTI_PHASE and the runtime refuses L or XL `none` without a reason.
- Review quality: the reviewer greps for the pattern a bug fix replaced, cites
  the fixing hunk and asks the resolved-state question in delta mode, always
  sees the whole recorded span, and the diff is reclassified before the delta
  pass; RCA confidence has a calibration table; `fix-bug` has its complexity
  signal table back; a `PASS` gate is never a stop signal; a shallow
  `CHANGES_REQUIRED` re-runs the validator at `deep-review` instead of
  revising the plan; on a single-provider machine the finding verifier runs on
  `deep-review` or the finding stays capped at `[minor]`.
- Restored `USER_DECISION` heuristics, the stop-on-no-logs rule in `fix-ci`,
  the per-unit `## Phase Complete` hard gate, and TRIVIAL-plus-CORE review
  escalation; `review-plan` and `fix-ci` record snapshot gates.

- Replaced the control plane: the parent session runs the cheap workhorse
  (Sonnet on Claude, Sol on Codex), classifies complexity (TRIVIAL / STANDARD /
  COMPLEX), size (S / M / L / XL), and execution shape, and drives goal
  workflows through `PASS / RETRY / ESCALATE / RECLASSIFY / USER_DECISION /
  BLOCKED` gates with a one-retry budget (`rules/gates.md`).
- Added the `PROJECT.md` v2 routing snapshot and `aitk project-state`
  (`init`, `show`, `set`, `gate`, `advance`, `phases`, `phase`) so resume and
  escalation read durable data; legacy `MODERATE` reads as `STANDARD`.
- Rewrote model routing: Sonnet implements, a new read-only `planning` route
  (Opus) plans only COMPLEX work, `review`/`rca` are independent specialists
  preferring the other provider, Fable stays a read-only deep advisor. Catalog
  moved to the Claude 5 family (Opus 5, Sonnet 5, Fable 5.1) and GPT-5.6 Sol.
- Added the native worker roster (`agents/claude/*.md`, `agents/codex/*.toml`,
  installed to `~/.claude/agents` and `$CODEX_HOME/agents`) and the
  provider-neutral specialist contracts in `agents/specialists/` that the route
  runner inlines for cross-provider review, RCA, and plan validation.
- Simplified review to one independent review, validate-before-fix, one delta
  pass, and at most two conditional deep lenses; retired review ensembles,
  verifier diversity, the resolved-state audit, and `aitk review-ensemble`.
- Replaced the 8/10 multi-reviewer plan loop and cold read with one
  independent validator returning `APPROVE / CHANGES_REQUIRED / REPLAN`, plus
  size-aware decomposition and just-in-time phase planning.
- Added the shared `verification-loop` skill, the RCA evidence gate with an
  independent RCA specialist, the observation queue in `reflection`, richer
  metrics fields, and an `evals/` corpus with a deterministic runner.
- Retired `action-gate`, `rules/review-gate.md`, `rules/stop-rules.md`,
  `rules/scoring.md`, and the manual context-clear dependency; fresh workers
  are the phase boundary and auto-compaction protects the parent.

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
