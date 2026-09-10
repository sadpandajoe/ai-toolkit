---
name: classify-diff
description: Analyze a changeset and return its file domains, risk flags, and which conditional deep lenses should run.
---

# Classify Diff

Deterministic risk routing for a review. The classifier reports facts; the
calling orchestration decides dispatch.

<!-- aitk-model-route-exempt:describes-caller-owned-dispatch -->
This reference never dispatches reviewers or launches workers itself; the
calling workflow owns orchestration.

## Inputs

The diff, the complexity from the Complexity Gate, the change title or commit
subjects when available, and any explicit ask (`--adversarial`, "deep review",
"deep quality", "code judo").

## Steps

1. **Classify files** into domains by path and content: Frontend (`*.tsx`,
   `*.jsx`, `*.vue`, `*.css`, `components/`), Backend (`*.py` non-test, `*.go`,
   `*.rs`, `*.java`, `api/`, `server/`), Tests (`*_test.*`, `*.test.*`,
   `tests/`, `conftest.py`), Infrastructure (`Dockerfile`, CI YAML,
   `terraform/`), Config (`*.toml`, `*.ini`, `.env*`, `settings.*`).

2. **Set risk flags.**
   - **Security-sensitive**: authentication or authorization, cryptography,
     unsanitized input, dynamic SQL or ORM input, secrets or tokens,
     permission checks, agent capability configuration (which model, effort,
     sandbox, permission mode, or tool list a worker runs under:
     `interfaces/model-routing.json`, `aitk/model_routing.py`,
     `aitk/routing_*.py`, `agents/`, hook
     and MCP config), worker context assembly (`aitk/routing_closure.py`,
     `aitk/routing_markdown.py`), or trust-boundary changes (publish or push
     authorization, sandbox enforcement, fail-closed checks becoming advisory:
     `aitk/routing_manifest.py`, `aitk/routing_resolver.py`,
     `aitk/routing_transport.py`, `aitk/installer.py`). Name the
     implementation files, not only a facade; extend this list in the same
     commit when a subsystem is decomposed.
   - **Architecture change**: new module boundaries, changed public contracts,
     new patterns, cross-subsystem data flow.
   - **Refactor-shaped**: title matches `^refactor` or mentions restructure,
     extract, decompose, clean up; or net-neutral line delta with high churn or
     renames and unchanged tests. Formatting sweeps, lock bumps, and generated
     churn are not refactors.
   - **Deep-tier escalation**: exactly the phrases **"deep review"**,
     **"deep quality review"**, **"thermonuclear"**, or `max`/`ultra` effort.
     This pins complexity to at least COMPLEX and routes the independent review
     on `deep-review`. A bare "deep quality" ask is a lens request, not an
     escalation.

3. **Select deep lenses** (at most two; the independent review always runs):

| Review Domain | Trigger | Skill |
|---|---|---|
| Adversarial | Security-sensitive, or an explicit adversarial ask | review/references/adversarial.md |
| Deep quality | Refactor-shaped, a "deep quality" ask, or deep-tier escalation | review/references/deep-quality.md |
| Architecture | Architecture change on STANDARD or COMPLEX | plan-review/references/architecture.md |

   When three would fire, drop the one whose domain the diff touches least and
   report it. Test quality, frontend, and backend checklists
   (`testing/references/review-tests.md`, `plan-review/references/frontend.md`,
   `plan-review/references/backend.md`) are inlined in the independent
   reviewer's contract and applied to the domains this classification reports.

4. **Code-judo lane**: `YES` only on deep-tier escalation, a `^refactor`
   title, or an explicit ask. It runs outside the findings lanes and returns
   proposals.

## Output

```markdown
## Diff Classification
Complexity: TRIVIAL | STANDARD | COMPLEX   (note when pinned by escalation)
Security-sensitive: YES | NO — <why>
Architecture change: YES | NO
Refactor-shaped: YES | NO
Deep-tier escalation: YES | NO
Code-judo lane: YES | NO
Deep lenses: <adversarial | deep-quality | architecture, or none> — <dropped lens and reason, if any>
Files analyzed: <count>

### File Domain Summary
| Domain | Files | Examples |
|--------|-------|----------|
```

## Notes

<!-- aitk-model-route-exempt:explicitly-not-a-dispatch -->
- This reference classifies; it does not dispatch reviewers or launch subagents.
- The trigger table is the single source of truth for deep lenses. Update it
  here, not in the orchestration references.
