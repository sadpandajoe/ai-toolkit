---
name: qa
description: Manual QA work — triage a loose bug report into a repro plan, validate a fix, assess change impact, discover or expand use cases, execute scenarios in a real environment, or file a bug report. Do NOT use for root-cause investigation (use debug/), writing automated tests (use testing/), or code review (use review/).
user-invocable: false
---

# QA

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella skill for repo-standard QA phases. The orchestrator picks the relevant phase from the decision tree below and reads the corresponding reference for steps + output template.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Bug triage | Pre-investigation: turn loose report into repro plan | [references/triage-bug.md](references/triage-bug.md) |
| Validate fix | Post-implementation: confirm bug resolved in user-visible flow | [references/validate-fix.md](references/validate-fix.md) |
| Validate feature | Post-implementation: confirm acceptance criteria in user-visible flow | [references/validate-feature.md](references/validate-feature.md) |
| Impact assessment | Code review: classify changeset as CORE / STANDARD / PERIPHERAL | [references/assess-impact.md](references/assess-impact.md) |
| Analyze use cases | Discovery: build use-case matrix from code + context | [references/analyze-use-cases.md](references/analyze-use-cases.md) |
| Expand scenarios | After fix is known: identify smallest extra checks for regression protection | [references/expand-scenarios.md](references/expand-scenarios.md) |
| Execute use cases | Run scenarios against a real environment with evidence capture | [references/execute-use-cases.md](references/execute-use-cases.md) |
| Manual PR test | Verify a PR in a running browser app | [references/test-pr/setup.md](references/test-pr/setup.md), [scenarios](references/test-pr/scenarios.md), [execute](references/test-pr/execute.md), [report](references/test-pr/report.md) |
| File bug | Strong failure signal needs a clean handoff (Shortcut posting included) | [references/file-bug.md](references/file-bug.md) |
| Write report | QA results need to land on a Shortcut/PR/Slack/email destination — canonical body shape and tone | [references/write-report.md](references/write-report.md) |

## Invocation Patterns

Most QA phases are checklist + output-template work the orchestrator does inline:

1. Read the relevant reference.
2. Follow its steps.
3. Emit its output block into the conversation.

When fresh context matters (long-running session, parallel work, separation from the implementation thread), spawn a `general-purpose` subagent and pass the reference content as the prompt. Each reference declares its recommended provider-neutral tier in frontmatter.

## Phase Composition

Common combinations:
- **Bug workflow** (`/fix-bug`): triage-bug → (implement) → validate-fix → optionally file-bug
- **Feature workflow** (`/create-feature`): feature acceptance criteria → validate-feature
- **Code review** (`/review-code`, `/review-pr`): assess-impact (always) → expand-scenarios (when reviewing a fix)
- **Test plan**: analyze-use-cases → expand-scenarios → execute-use-cases
- **PR smoke test** (`/test-pr`): test-pr/setup → assess-impact → pr-smoke-scenarios → test-pr/execute → test-pr/report

## Notes

- References hold the per-phase steps and output templates. SKILL.md only routes.
- Environment prep lives in the `preflight` skill (`preflight/references/prepare-environment.md`) — used outside QA contexts too (implementation env prep). Triage and validate-fix link to it when env prep is required.
- `file-bug` includes the Shortcut posting protocol for workflows that push results back.
