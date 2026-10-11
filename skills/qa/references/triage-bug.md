# Triage Bug

Use at the start of a bug workflow to decide whether the report is
reproducible, what evidence exists, and what setup is required. For UI and
workflow bugs this is two-stage: a first pass from the report, logs,
screenshots and context, then full reproduction once the app or target
environment is ready.

1. Restate the reported problem in user-facing terms.
2. Identify the environment, data, feature flags, and accounts needed to reproduce it.
3. Attempt a fast first-pass reproduction or explain why it cannot be reproduced yet.
4. When reliable reproduction needs a running app, use superset-local for
   Superset; otherwise start only the services the repro needs and record
   blockers.
5. For UI paths, drive the repro with the available browser automation once the app is runnable.
6. Record expected versus actual behavior, the artifacts that raise
   confidence (screenshots, logs, failing steps, URLs), and the gaps that
   block reliable validation.

## Output

```markdown
## QA Triage

- Bug status: <confirmed / plausible / not reproduced / insufficient evidence>
- Repro phase: <first-pass only / fully reproduced / blocked on environment>
- Repro steps: <numbered steps or blockers>
- Expected behavior: <what should happen>
- Actual behavior: <what happens instead>
- Environment needs: <data, flags, accounts, browsers, services>
- Browser automation: <required / useful / not needed>
- Evidence: <key proof points>
- Open gaps: <what still blocks reliable validation>
```
