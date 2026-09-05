# Changelog

## 0.3.0 — 2026-09-05

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
