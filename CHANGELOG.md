# Changelog

## 0.1.0 — 2026-07-15

- Moved all daily workflow procedures from commands into a canonical provider-neutral workflow skill.
- Added the deterministic `aitk` build, route, list, doctor, and conformance interfaces.
- Added safe idempotent Claude/Codex guidance and skill installation while preserving unrelated user configuration.
- Added a validated Codex plugin manifest, Agent Skills metadata, and provider-neutral lifecycle hooks.
- Added routing, safety, installer, build, portability, resume, and behavioral contract tests.
- Standardized local metrics under `.ai-toolkit/metrics.jsonl` with legacy-read migration.
- Removed personal paths, unsafe secret diagnostics, `eval` retries, destructive RBAC defaults, and provider primitives from shared workflows.
- Migrated the optional PGM reports to a manifest-backed Agent Skill with generated aliases, opt-in routing, and reversible installation.
- Added SHA-pinned CI that runs the same complete conformance gate as local development on Python 3.11 and 3.14.
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
