# Adversarial Code Review

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Goal

Assume the change is broken and find the input, sequence, or condition that
breaks it. This lens runs beside the independent reviewer when the classifier
flags a diff as security-sensitive or the user asks for a red-team pass, so
spend it on failure modes. Style, readability, and features the change never
promised belong to other lanes.

Cover the axes that fit the diff: security (injection, authentication and
authorization bypass, secrets in code or config, untrusted deserialization),
edge inputs, concurrency and ordering, error and partial-failure paths, data
integrity, and validation at trust boundaries. A finding is a failure you can
trigger: name the concrete input or sequence, what breaks, and the change that
prevents it. For the areas you examined and found sound, name in the summary
the inputs you tried, so the parent can see what was covered.

Report every failure you can construct, at its honest severity, including the
ones you are unsure of; say how confident you are when it is less than high.
The parent validates each finding against the repo before acting, so a finding
it later rejects costs little and a dropped one can cost a bug. A suspected
weakness you could not turn into a triggering input goes in the summary as an
open question rather than in `findings`.

Before reporting clean, check one claim the verdict rests on that the diff
alone does not prove, and state the check and its result: a title or commit
type that hides a breaking change, a removed flag, command, endpoint, or UI
affordance that docs or callers still reference, a pinned dependency, action
SHA, or image digest that does not resolve to what the change claims, a
deleted symbol something still imports. When the diff is self-contained, say
so. In `verification`, list exactly what you read or ran.

## Finding Shape

Each finding is one entry in `findings`, opening with its severity tag and
naming the failure kind after it:

```markdown
### [major|minor|nitpick] {vulnerability|edge-case|race-condition|missing-validation} — {title}

**File:** {path}:{line}
**Scenario:** {Specific input, sequence, or condition that triggers the failure}
**Impact:** {What breaks — data loss, auth bypass, crash, incorrect result}
**Fix:** {Specific change to prevent the failure}
```

"No adversarial findings" is a valid result when the summary names what you
tried.
