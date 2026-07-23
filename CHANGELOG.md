# Changelog

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
