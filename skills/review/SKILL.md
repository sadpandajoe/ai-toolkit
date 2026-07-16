---
name: review
description: "Umbrella for code review (shipped code): orchestration, classifier, reviewer lenses (code-quality, adversarial), and PR posting helpers."
user-invocable: false
disable-model-invocation: true
---

# Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for code-review work — review of *shipped code*, not plans. References are grouped by role so commands can load only the phase they are entering.

## Orchestration

| Reference | Role |
|-----------|------|
| [references/local-review.md](references/local-review.md) | Local `/review-code` orchestration |
| [references/pr-review.md](references/pr-review.md) | Single GitHub PR review procedure |
| [references/pr-batch.md](references/pr-batch.md) | Batch PR review orchestration |
| [references/adversarial-orchestration.md](references/adversarial-orchestration.md) | `/review-code-adversarial` orchestration |
| [references/workflow-review.md](references/workflow-review.md) | Standard-tier Workflow orchestration (lens fan-out → dedup → adversarial verify) |

## Classifiers

| Reference | Role |
|-----------|------|
| [references/classify-diff.md](references/classify-diff.md) | Read diff + complexity tier, return which reviewer domains should activate |

## Posting Helpers

| Reference | Role |
|-----------|------|
| [references/pr-posting.md](references/pr-posting.md) | GitHub review posting and summary rules |

## Reviewer Lenses

| Lens | When | Reference |
|------|------|-----------|
| Code quality | Always (every complexity tier) | [references/code-quality.md](references/code-quality.md) |
| Adversarial | Security-sensitive diffs; `/review-code-adversarial` command | [references/adversarial.md](references/adversarial.md) |

## Distinction vs Other Umbrellas

- **review/** (this skill) — reviews code (post-implementation)
- **plan-review/** — reviews plans (pre-implementation)
- **testing/** — includes `review-tests` + `review-testplan` (test-harness-specific reviewers)
- **qa/** — scenario-level critique (bug triage, validation)

The `/review-code` command dispatches through `classify-diff`, which chooses lenses from this umbrella **and** the `testing/` umbrella when tests are in scope.

The `/review-pr` command uses `pr-review`, `pr-batch`, and `pr-posting` for PR-specific context gathering and GitHub interaction, then dispatches the same reviewer lenses as `/review-code`.

## Invocation

Reviewer lens references are subagent prompts. Orchestration and posting references are read by the main thread.

Dispatch mode is tier-routed:

- **TRIVIAL / MODERATE** — direct Agent-tool spawns from the main thread:

  ```
  Agent(subagent_type: "general-purpose", prompt: "Tier: Heavy\n<reference contents>")
  ```

- **STANDARD** (or ≥3 triggered lanes) — Workflow orchestration per [references/workflow-review.md](references/workflow-review.md): lens fan-out → dedup → adversarial verify off-thread; only confirmed findings return to the session. The command invocation is the Workflow opt-in.

Map the tier to the current runtime's actual model or reasoning-effort controls at dispatch time.

## Notes

- `classify-diff` has a different shape from the reviewer references (it's a classifier, not a reviewer). Grouped here because reviewer dispatch is the head of the review workflow.
- Reviewer lens descriptions declare their own reasoning-load hints in frontmatter for subagent spawning.
