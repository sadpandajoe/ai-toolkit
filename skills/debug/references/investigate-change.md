---
name: investigate-change
description: Investigate or run RCA on broken behavior as an internal phase of a larger workflow. Identifies root cause with evidence and hands a compact summary back. Use the "When Investigating a Bug" section for bug-specific framing fields. Internal helper.
user-invocable: false
disable-model-invocation: true
tier: Heavy
---

# Investigate Change

Use this phase when a workflow needs investigation or root-cause analysis as an internal step rather than as a standalone user-facing command.

## Goal

Understand what is broken, identify the most plausible root cause with evidence, and hand the result back to the calling workflow.

## Scope

Use this for:

- code-level behavior investigation
- local root-cause analysis
- validating whether a suspected fix already exists
- narrowing failure scope before planning or adaptation

This file is the reusable RCA phase for larger workflows. Use it when the public action is still `fix-bug`, `create-feature`, or another end-to-end command.

## Core Steps

1. Define the problem precisely.
2. Reproduce if possible.
3. Use git history early: inspect blame, logs, and recent changes before settling
   on a cause. Scope git searches to master and the current branch — do not use
   `git log --all` (unmerged branches may contain experimental or unvetted code).
4. Identify the most likely introducing change. When restoring removed or commented-out code, trace the removal commit on master and inspect its parent (`git show <sha>^:<file>`) rather than searching other branches.
5. Check whether an equivalent fix already exists.
6. Name the regression test that should fail before the fix and pass after it,
   or record why that proof is not currently practical.
7. Summarize root cause, evidence, and open uncertainty. Separate the incident
   root cause from latent bugs or opportunistic hardening so the causal chain
   remains clear. Preserve that distinction in PROJECT.md and carry it into a
   later bug-fix PR description: **Incident Root Cause**, **Latent Bugs /
   Hardening** when present, then **Fix**.

## Output

Return a compact handoff:

```markdown
## Investigation Summary

- Problem: <what is broken>
- Root cause: <most likely cause>
- Latent bugs / hardening: <separate findings, or none>
- Evidence: <key proof points>
- Existing fix: <yes/no and where>
- Open questions: <remaining uncertainty>
```

## When Investigating a Bug

A bug investigation is the same process as above, with three extra expectations for how you frame the work:

1. **Restate the reported problem in code-level terms** — trace from the user-visible symptom to the code path responsible.
2. **Attempt local reproduction when practical** — if reproduction is not possible, explain why and what indirect evidence substitutes.
3. **Frame findings in terms of user impact** — connect the root cause back to the observable failure the user reported.

And extend the output with these fields:

- **Affected area**: files, services, or flows involved
- **Introducing change**: commit or PR that introduced the regression, or "unknown"
- **Existing local safeguards**: tests, guards, or defensive checks that should have caught this (present / absent / partial)

Full extended output:

```markdown
## Bug Investigation

- Problem: <user-visible symptom, in code-level terms>
- Affected area: <files, services, flows>
- Likely root cause: <most plausible cause>
- Latent bugs / hardening: <separate findings, or none>
- Evidence: <key proof points>
- Introducing change: <commit / PR / unknown>
- Existing local safeguards: <present / absent / partial>
- Existing fix: <yes/no and where>
- Open questions: <remaining uncertainty>
```
