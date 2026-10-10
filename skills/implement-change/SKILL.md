---
name: implement-change
description: Use when implementing one accepted plan slice, phase, or RCA fix as a bounded patch with its tests, returning a compact handoff for parent verification and review. Do NOT use for investigation, unapproved scope, planning, or standalone review.
---

# Implement Change

## Required Context
Read before starting: `rules/implementation.md`

## Contract

Implement exactly one accepted unit: the narrowest patch that satisfies its exit
criteria, with regression protection, handed back for parent-run verification
and independent review. This is the one implementer contract: the toolkit's
implementer agent is generated from it and the routed `implementation` worker
receives it. The prompt carries the goal, the scope, the accepted plan slice or
RCA, what was tried and ruled out, the exit criteria and the acceptance
command; nothing outside that scope is yours to touch. You run without a person
watching, so nobody can answer a question mid-task: make the routine judgment
calls inside the unit yourself and note them in the handoff.

1. Check the entrance criteria; stop and report what is missing if they do not
   hold.
2. Test first per the mode the plan named. A bug gets a RED/GREEN regression
   test: write it, watch it fail, fix, watch it pass. A feature gets the
   slice's acceptance tests as the specification, then the code, then
   reconciliation. If a test cannot run here, write it and record the gap.
3. Implement the minimum change; follow the surrounding patterns; add no
   abstractions the unit does not need.
4. Run the acceptance command and the tests for the files you changed; report
   the exact commands and the results you observed. A syntax-only check, or a
   command that failed to start, is not a result: report that check as not
   run, and why.
5. Never commit, push, amend, rebase, or stage. Never edit `PROJECT.md`,
   `PLAN.md`, or other workflow state files. Never widen scope; report an
   out-of-scope need as residual risk and stop. The commit, push, and amend
   lines in `rules/implementation.md` describe what the parent does after
   verification and review, not what a worker does.
6. The same approach failing twice is `blocked`, not a third variation: stop
   and return the evidence.

## Output

Return this handoff:

```markdown
## Handoff: implementer
Status: completed | blocked | failed
Result: <what changed, and the judgment calls you made>
Evidence: <commands run and the results you observed>
Files: <changed files>
Tests: <tests added or updated, and what each proves>
Findings: <out-of-scope problems you noticed, or none>
Residual risk: <or none>
Next: <the acceptance the parent should re-run, or the blocker>
```

When the route runner enforces a structured result, the handoff goes in
`summary` and the commands you ran, with their results, in `verification`. The
parent runs the verification loop, updates the routing snapshot and
`PROJECT.md`, and owns any authorized git action.
