# Investigate Change

Use this phase when a workflow needs investigation or root-cause analysis as an internal step rather than as a standalone user-facing command: code-level behavior investigation, local root-cause analysis, checking whether a suspected fix already exists, or narrowing failure scope before planning or adaptation. The public action is still `fix-bug`, `create-feature`, or another end-to-end command.

## Goal

Find what is broken and why, with evidence strong enough for the RCA gate ([review-rca.md](review-rca.md)): the mechanism explained rather than correlated, competing causes ruled out or listed as open, and a regression check that fails before the fix and passes after, or the reason that proof is not practical. Trace the reported symptom to the code path behind it, reproduce it locally when practical, and say what indirect evidence stands in when you cannot.

Three things that are easy to get wrong:

- Use git history early (blame, log, recent changes), scoped to the main branch and the current branch. Do not use `git log --all`: unmerged branches may contain experimental or unvetted code that never shipped. To restore removed or commented-out code, find the removal commit on the main branch and read its parent (`git show <sha>^:<file>`) rather than searching other branches.
- Check whether an equivalent fix already exists ([check-existing-fix.md](check-existing-fix.md)).
- Keep the incident root cause separate from latent bugs or opportunistic hardening so the causal chain stays clear. Preserve that distinction in PROJECT.md and carry it into a later bug-fix PR description: **Incident Root Cause**, **Latent Bugs / Hardening** when present, then **Fix**.

## Output

Return the debugger handoff the RCA gate grades:

```markdown
## Handoff: debugger
Status: completed | blocked
Problem: <symptom in code-level terms>
Root cause: <mechanism, or "not established">
Confidence: <n>/10 — <why>
Evidence: <key proof points with file:line or command>
Alternatives ruled out: <cause — evidence>, or "none considered"
Introducing change: <sha/PR or unknown>
Regression check: <test or command that fails before and passes after>
Latent findings: <separate list, or none>
Existing fix: <none found, or the commit or PR>
Next: <fix scope suggestion, or the investigation still needed>
```
