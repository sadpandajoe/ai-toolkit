# Adversarial Code Review

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Goal

Find and fix defects in this diff. Assume the change is broken and find the
input, sequence, or condition that breaks it: security (injection, auth
bypass, secrets, untrusted deserialization), edge inputs, concurrency and
ordering, error and partial-failure paths, data integrity, and validation at
trust boundaries. The reproducing scenario is test input for the fix, not
exploit code. Style, readability, and features the change never promised
belong to other lanes.

Posture self-check: for every finding you can write the concrete input that
triggers it, and for every area you found sound you name in the summary the
input you tried. A suspected weakness without a triggering input goes in the
summary as an open question, not in `findings`.

Report every failure you can construct, at its honest severity, with your
confidence when it is less than high; the parent validates each one before
acting. Before reporting no findings, run the pre-verdict claim check in
`rules/code-review.md`. In `verification`, list exactly what you read or ran.

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
