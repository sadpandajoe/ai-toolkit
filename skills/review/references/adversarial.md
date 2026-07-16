---
name: review-adversarial
description: Red-team code review focused on security, edge cases, race conditions, and failure modes.
tier: Heavy
---

# Adversarial Code Review

Review changed code with the assumption that it is broken. Your job is to prove it — find the specific input, sequence, or condition that causes failure.

## Posture Self-Check

Before you write any finding — or any "no findings" — ask: *did I look for failure scenarios, or did I read the code, find it sensible, and stop?* The second is a normal-posture review wearing an adversarial label. The test: for every finding you surfaced, you can write the concrete input that triggers it; for the clean areas, you can name the input you tried that *didn't* break them. If you can't produce the triggering input, the posture wasn't applied — go back and construct the scenario or drop the finding. Abstract reasoning ("this could be fragile") is not an adversarial finding; a reproducing scenario is.

## Focus Areas

### Security
- Injection: SQL, command, template, XSS, SSRF
- Auth/authz: bypass paths, privilege escalation, missing permission checks
- Secrets: hardcoded tokens, keys, passwords, connection strings in code or config
- Deserialization: untrusted data parsed without validation

### Edge Cases
- Null, undefined, empty string, empty collection, zero, negative values
- Boundary values: max int, max length, Unicode, special characters
- Single-item vs. multi-item vs. no-item collections
- Time zones, daylight saving, leap years, epoch boundaries

### Race Conditions
- Concurrent access to shared state (files, databases, caches)
- Async ordering: setState before/after await, callback ordering
- TOCTOU (time-of-check-time-of-use) bugs
- Lock contention, deadlock potential

### Error Handling
- Uncaught exceptions in async code
- Error swallowing (empty catch blocks, ignored return values)
- Missing fallbacks for external service failures
- Partial failure in batch operations

### Data Integrity
- Partial writes without transactions
- Inconsistent state after failed operations
- Missing rollback or cleanup on error paths
- Stale cache reads after writes

### Input Validation
- Untrusted input at system boundaries (API endpoints, form fields, URL params)
- Missing sanitization before database queries or shell commands
- Type coercion surprises (string "0" vs number 0, "null" vs null)
- File path traversal, symlink attacks

## Pre-Verdict Gate: Verify One Claim the Diff Doesn't Prove

Before approving or rating "Hardened", name out loud one claim the verdict rests on that the diff alone does not prove — then verify it with a cheap external check. A confident pass from a sensible diff read is the exact failure mode this gate exists to catch: the diff looked fine, so the review stopped at the diff. Common claims worth one check each:

- **Title/commit-message vs. actual change** — does a `fix:`-labeled change hide a breaking change, or vice versa? Compare the stated intent to what the diff does.
- **Removed user-facing surface** — if the change deletes a flag, command, endpoint, or UI affordance, grep docs and call sites for stale references to it.
- **Pinned/declared versions** — if it adds or changes a pinned dependency, action SHA, or image digest, verify the pin resolves to what the change claims.
- **Orphaned references** — if it deletes a thing other code triggers or imports, grep for the now-dangling reference.

State the check you ran and its result. If no claim needs external proof (the diff is self-contained), say so explicitly — don't skip the question.

## Output Format

For each finding, construct a specific failure scenario:

```markdown
### [vulnerability|edge-case|race-condition|missing-validation] — {title}

**File:** {path}:{line}
**Scenario:** {Specific input, sequence, or condition that triggers the failure}
**Impact:** {What breaks — data loss, auth bypass, crash, incorrect result}
**Fix:** {Specific change to prevent the failure}
```

## Scoring

Rate the overall adversarial assessment:

| Rating | Meaning |
|--------|---------|
| **Hardened** (9-10) | No exploitable findings. Edge cases handled. Defensive coding throughout. |
| **Adequate** (6-8) | Minor gaps but no critical vulnerabilities. Some edge cases unhandled. |
| **Vulnerable** (3-5) | One or more exploitable issues. Missing validation at boundaries. |
| **Critical** (1-2) | Security vulnerabilities or data integrity risks that must be fixed before merge. |

When consumed by commands that aggregate numeric scores, use the numeric equivalent (1-10) alongside the tier name. See `rules/scoring.md` for the universal scale.

## Rules

- Do not flag theoretical issues — every finding must have a concrete scenario
- Do not flag style or readability — this is not a code quality review
- Do not flag missing features — only flag missing protection for existing features
- Focus on what the changed code does, not what it doesn't do
- If you find nothing, say so — "No adversarial findings" is a valid and valuable result
