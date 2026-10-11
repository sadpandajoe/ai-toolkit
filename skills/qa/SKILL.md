---
name: qa
description: Manual QA work — triage a loose bug report into a repro plan, validate a fix or feature, assess change impact, run PR smoke scenarios in a real environment, file a bug report, or write a QA report. Do NOT use for root-cause investigation (use debug/), writing automated tests (use testing/), or code review (use review/).
---

# QA

Umbrella for QA phases. The orchestrator reads the phase reference it needs
and emits its output block.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Bug triage | Pre-investigation: turn loose report into repro plan | [references/triage-bug.md](references/triage-bug.md) |
| Validate | Post-implementation: confirm a fix or acceptance criteria in the user-visible flow | [references/validate.md](references/validate.md) |
| Impact assessment | Code review: classify changeset as CORE / STANDARD / PERIPHERAL | [references/assess-impact.md](references/assess-impact.md) |
| PR smoke scenarios | Derive focused scenarios from a PR | [references/pr-smoke-scenarios.md](references/pr-smoke-scenarios.md) |
| Manual PR test | Verify a PR in a running browser app | [references/test-pr/setup.md](references/test-pr/setup.md), [scenarios](references/test-pr/scenarios.md), [execute](references/test-pr/execute.md), [report](references/test-pr/report.md) |
| Browser recording | Record UI evidence | [references/browser-recording.md](references/browser-recording.md) |
| File bug | Strong failure signal needs a clean handoff | [references/file-bug.md](references/file-bug.md) |
| Write report | QA results go to a Shortcut/PR/Slack/email destination | [references/write-report.md](references/write-report.md) |

<!-- aitk-model-route:qa.fresh-validation -->
When fresh context matters (long-running session, parallel work, separation from the implementation thread), spawn a subagent on `review` for validation judgment or `operations` for deterministic evidence collection and pass the reference content as the prompt.

## Consumers

- `fix-bug`: triage-bug, then validate.
- `create-feature`: validate.
- `review-code`, `review-pr`: assess-impact.
- `test-pr`: setup → assess-impact → pr-smoke-scenarios → execute → report.
- `run-test-plan`: browser-recording and write-report.

When a phase needs a running app, use superset-local for Superset; otherwise
start only the services the repro needs and record blockers.
