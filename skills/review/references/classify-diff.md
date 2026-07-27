---
name: classify-diff
description: Analyze a changeset and return which review domains are relevant, with trigger reasons.
tier: Standard
---

# Classify Diff

Deterministic reviewer routing. Read the changeset and return which review domains should be activated, why each triggered, and whether the diff is security-sensitive.

<!-- aitk-model-route-exempt:describes-caller-owned-dispatch -->
This skill replaces inline reviewer-selection logic in commands. The calling workflow dispatches subagents based on this skill's output — this skill classifies, the command orchestrates.

## Required Context

The caller provides:
- The diff (staged, unstaged, or commit range)
- The complexity tier (`TRIVIAL`, `MODERATE`, or `STANDARD`) from the Complexity Gate
- The requested review effort, if the command supplied one (`high` / `max` / `ultra`). Treat an explicit **deep-tier phrase** as `ultra` — these are escalation phrases, not route names.
- The change title / commit subjects, when available (PR title or commit messages)

### Deep-tier phrases (canonical list)

The deep-tier phrase list is exactly:

> **"deep review"** · **"deep quality review"** · **"thermonuclear"**

Those three phrases, plus `max`/`ultra` effort, are the *only* things that set `Deep-tier escalation: YES`. This file owns the list; every other rule here and in the consuming orchestrators refers back to it rather than re-listing the phrases.

**A bare "deep quality" ask is deliberately *not* on that list.** It names the [deep-quality lens](deep-quality.md) — strict structural findings on the cheap `review` route — so it fires that one lens and changes nothing else. Match the longest phrase: "deep quality review" is a deep-tier escalation, "deep quality" alone is a lens request. The one-word difference is load-bearing: the first buys the whole review at deep tier, the second buys one cheap lens.

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
| Deep quality | Refactor-shaped diff (see step 3a) OR any STANDARD-tier diff; always under deep-tier escalation or a bare "deep quality" lens ask. Strict structural findings on the cheap `review` route. | `review/references/deep-quality.md` |
| Code-judo | Deep-tier escalation OR title matches `^refactor` OR an explicit Code-judo ask. Generative restructuring proposal — routes to `deep-review` (see review SKILL Invocation). A `^refactor` title auto-fires; the refactor **shape signal alone** (step 3a, no `^refactor` title) is **advisory** — recommend it, do not auto-fire. | `review/references/code-judo.md` |
| Architecture | STANDARD + logic changes in source files; MODERATE only when ownership/design placement is unclear | `plan-review/references/architecture.md` |
| Tests | MODERATE or STANDARD + test files exist in diff OR test files exist for changed source files | `testing/references/review-tests.md` |
| Test plan | MODERATE or STANDARD + behavior changed AND no test files exist in diff AND no test files found for changed source files | `testing/references/review-testplan.md` |
| Frontend | MODERATE or STANDARD + frontend files changed | `plan-review/references/frontend.md` |
| Backend | MODERATE or STANDARD + backend files changed | `plan-review/references/backend.md` |

**3a. Detect refactor shape** (feeds the Deep quality and Code-judo rows). Compute from the diff and title:
- **Title signal**: change title / commit subject matches `^refactor` (conventional-commit prefix) or contains "restructure", "extract", "decompose", "clean up".
- **Shape signal**: net-neutral or negative line delta with high churn, a high rename ratio (`git diff --find-renames`), or moves without new public surface, **and** tests unchanged.
- A change is **refactor-shaped** if the title signal fires, or the shape signal fires on a non-TRIVIAL diff.
- **False-positive guard**: pure formatting sweeps, dependency-lock bumps, and generated-file churn are *not* refactors even when net-neutral — exclude them from the shape signal.

Rules:
- Code quality **always** triggers regardless of complexity tier.
- **Deep quality vs Code-judo (cost discipline).** Deep quality is *findings* on the cheap `review` route — auto-fire it on refactor shape or STANDARD. Code-judo is a *generative* pass on the expensive `deep-review` route — auto-fire it only on high-confidence intent (deep-tier escalation, `^refactor` title, or an explicit Code-judo ask). When only the shape signal fires, **recommend** Code-judo in the output ("looks like a refactor — consider a code-judo pass") rather than triggering it; do not spend the deep tier on a heuristic guess.
- TRIVIAL diffs never **auto**-trigger Deep quality or Code-judo by tier or shape alone (a rename or one-liner needs neither). Explicit asks still fire on TRIVIAL, each to its own scope: a bare "deep quality" ask fires the Deep quality lens only; a Code-judo ask fires the Code-judo lane only; deep-tier escalation fires both.
- **Deep-tier escalation.** When effort is `ultra`/`max` or the request carries a deep-tier phrase (see *Deep-tier phrases* above), report that deep-tier escalation applies: the orchestrator routes *every* triggered lens through the `deep-review` route and adds the Code-judo lane. Escalation is *sufficient* for the Code-judo lane, not necessary — a `^refactor` title or an explicit Code-judo ask triggers the lane on its own with escalation `NO`. classify-diff only flags both facts; the review SKILL Invocation owns the routing (see its Deep review mode section).
- TRIVIAL complexity: code quality reviewer only **by default** — this is the baseline when no explicit escalation applies. Explicit asks and deep-tier escalation still fire the deep lenses (per the TRIVIAL rule above), and impact or security sensitivity can escalate the tier.
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
Deep-tier escalation: YES / NO   (YES only on `max`/`ultra` effort or a deep-tier phrase — the orchestrator then routes every triggered lens through `deep-review`)
Code-judo lane: YES / NO         (YES iff a Code-judo row appears in Triggered Reviewers below — set by escalation, a `^refactor` title, or an explicit Code-judo ask. Orchestrators dispatch the judo pass on this field, never on the escalation field.)
Files analyzed: [count]

### Triggered Reviewers
| Review Domain | Trigger Reason | Skill |
|---------------|----------------|-------|
| Code quality | Always | review/references/code-quality.md |
| [domain] | [specific trigger reason] | [skill file] |

Code-judo appears here as a row like any other triggered domain (trigger reason: deep-tier escalation, `^refactor` title, or explicit ask) — the `Code-judo lane` field above must agree with its presence. It is nonetheless dispatched outside the findings fan-out, on the `deep-review` route; the orchestrator owns that split.

### Advisory (not triggered)
- [Only when refactor shape fired without high-confidence intent] Looks like a refactor — consider a code-judo pass (`review/references/code-judo.md`, deep-review route). Omit this section when empty.

### File Domain Summary
| Domain | Files | Examples |
|--------|-------|---------|
| Frontend | [N] | [top 3 paths] |
| Backend | [N] | [top 3 paths] |
| Tests | [N] | [top 3 paths] |
```

## Notes
<!-- aitk-model-route-exempt:explicitly-not-a-dispatch -->
- This skill classifies — it does not dispatch reviewers or launch subagents. The calling workflow owns orchestration.
- File domain detection uses path patterns first, content signals second. When a file matches multiple domains (e.g., a test for a frontend component), classify it under each applicable domain.
- The trigger table is the single source of truth for which reviewers activate. If the table needs updating (new reviewer, new trigger), update it here rather than in individual commands.
- This skill owns two independent predicates, and downstream orchestration (the review SKILL Invocation, `local-review.md`, `pr-review.md`, `review-pr.md`) consumes each without re-deriving it:
  - **Deep-tier escalation** — `max`/`ultra` effort or a deep-tier phrase. Controls *which route* every triggered lens runs on.
  - **Code-judo lane** — escalation, a `^refactor` title, or an explicit Code-judo ask. Controls *whether the generative pass runs at all*. Because a `^refactor` title fires it alone, orchestrators must key judo dispatch on `Code-judo lane`, not on `Deep-tier escalation`.
- The canonical deep-tier phrase list lives in *Deep-tier phrases* above and nowhere else, so the predicate cannot drift between the classifier and the orchestrators that read it. When adding a phrase, add it there only.
