# Scoring Rubric

Shared scoring scale for all review skills that output `Score: X/10`.

## Scale

| Range | Tier | Meaning |
|-------|------|---------|
| **9-10** | Clean / Ready | No blocking issues. Only nitpicks or stylistic preferences. Safe to proceed. |
| **6-8** | Workable | Minor gaps but no critical or structural problems. Proceed with noted improvements. |
| **3-5** | Significant Issues | One or more structural, correctness, or coverage problems that should be resolved before proceeding. |
| **1-2** | Blocking | Fundamental flaws, security risks, or missing core requirements. Must be addressed. |

## Iteration Threshold

Review commands (`review-plan`, `create-feature`) iterate until all reviewers reach **8/10 or better**. A score of 6-7 is a pass-with-reservations — it does not block but signals meaningful gaps. Below 6 is a blocking signal that requires revision.

## Component Scoring

Some reviews score sub-components (e.g., Root Cause, Solution, Tests, Code, Docs). Apply the same scale per component. A single 1-2 on any component that represents a blocking issue should pull the overall score into the 3-5 range or lower — the overall is not a simple average.

## Adversarial Mapping

The adversarial review skill uses domain-specific tier names that map to these numeric ranges:

| Adversarial Tier | Numeric Range |
|------------------|---------------|
| Hardened | 9-10 |
| Adequate | 6-8 |
| Vulnerable | 3-5 |
| Critical | 1-2 |

When an adversarial review is consumed by a command that aggregates numeric scores, use the numeric equivalent alongside the tier name.
