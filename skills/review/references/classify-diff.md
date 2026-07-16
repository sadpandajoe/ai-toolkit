---
name: classify-diff
description: Analyze a changeset and return which review domains are relevant, with trigger reasons.
tier: Standard
---

# Classify Diff

Deterministic reviewer routing. Read the changeset and return which review domains should be activated, why each triggered, and whether the diff is security-sensitive.

This skill replaces inline reviewer-selection logic in commands. The calling workflow dispatches subagents based on this skill's output — this skill classifies, the command orchestrates.

## Required Context

The caller provides:
- The diff (staged, unstaged, or commit range)
- The complexity tier (`TRIVIAL`, `MODERATE`, or `STANDARD`) from the Complexity Gate

## Steps

1. **Gather the changeset**: Read the diff. Identify all changed files with their paths and change types (added, modified, deleted, renamed).

2. **Classify each file** into domains based on path patterns and content:

| Domain | File Signals | Content Signals |
|--------|-------------|-----------------|
| Frontend | `*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, `*.scss`, `components/`, `pages/`, `views/` | React hooks, state management, DOM manipulation, CSS-in-JS |
| Backend | `*.py` (non-test), `*.go`, `*.rs`, `*.java`, `api/`, `server/`, `handlers/`, `middleware/` | Route definitions, DB queries, auth logic, API handlers |
| Tests | `*_test.*`, `*.test.*`, `*.spec.*`, `test_*`, `tests/`, `__tests__/`, `conftest.py` | Test assertions, mocks, fixtures, test utilities |
| Infrastructure | `Dockerfile`, `*.yml`/`*.yaml` (CI/CD), `terraform/`, `k8s/`, `.github/workflows/` | Pipeline configs, deploy scripts, container definitions |
| Config | `*.json` (config), `*.toml`, `*.ini`, `.env*`, `settings.*` | Environment variables, feature flags, connection strings |

3. **Determine review domains** by mapping file domains to reviewers:

| Review Domain | Trigger | Skill |
|---------------|---------|-------|
| Code quality | Always | `review/references/code-quality.md` |
| Architecture | STANDARD + logic changes in source files; MODERATE only when ownership/design placement is unclear | `plan-review/references/architecture.md` |
| Tests | MODERATE or STANDARD + test files exist in diff OR test files exist for changed source files | `testing/references/review-tests.md` |
| Test plan | MODERATE or STANDARD + behavior changed AND no test files exist in diff AND no test files found for changed source files | `testing/references/review-testplan.md` |
| Frontend | MODERATE or STANDARD + frontend files changed | `plan-review/references/frontend.md` |
| Backend | MODERATE or STANDARD + backend files changed | `plan-review/references/backend.md` |

Rules:
- Code quality **always** triggers regardless of complexity tier.
- TRIVIAL complexity: code quality reviewer only unless impact or security sensitivity escalates.
- MODERATE complexity: triggered lanes only; do not launch the full review team just because one lane triggers.
- STANDARD complexity: launch all triggered lanes, include architecture for logic changes, and consider optional second opinion.
- Frontend and Backend are additive for MODERATE/STANDARD diffs — both can trigger on the same diff.
- Tests and Test Plan are mutually exclusive — if tests exist, use Tests; if not, use Test Plan.
- Security-sensitive diffs escalate to STANDARD handling even when initial size signals look MODERATE.

4. **Assess security sensitivity**: Flag as security-sensitive if the diff touches:
   - Authentication or authorization logic
   - Cryptographic operations
   - User input handling without sanitization
   - SQL queries or ORM calls with dynamic input
   - Secret management, token handling, or credential files
   - Permission checks or access control

## Output

```markdown
## Diff Classification

Complexity: TRIVIAL / MODERATE / STANDARD
Security-sensitive: YES / NO
Files analyzed: [count]

### Triggered Reviewers
| Review Domain | Trigger Reason | Skill |
|---------------|----------------|-------|
| Code quality | Always | review/references/code-quality.md |
| [domain] | [specific trigger reason] | [skill file] |

### File Domain Summary
| Domain | Files | Examples |
|--------|-------|---------|
| Frontend | [N] | [top 3 paths] |
| Backend | [N] | [top 3 paths] |
| Tests | [N] | [top 3 paths] |
```

## Notes
- This skill classifies — it does not dispatch reviewers or launch subagents. The calling workflow owns orchestration.
- File domain detection uses path patterns first, content signals second. When a file matches multiple domains (e.g., a test for a frontend component), classify it under each applicable domain.
- The trigger table is the single source of truth for which reviewers activate. If the table needs updating (new reviewer, new trigger), update it here rather than in individual commands.
