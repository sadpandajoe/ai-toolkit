# RCA Gate

The RCA gate decides whether a root-cause story is evidenced enough to plan a
fix. The parent grades STANDARD bugs itself; an independent specialist grades
COMPLEX or uncertain ones.

## The PASS list and the record

The PASS list and the RCA record shape live in `agents/specialists/rca.md`;
the parent and the specialist grade against the same list.

## Parent grading (STANDARD)

Grade the investigation's RCA record against the PASS list. Every item
evidenced → `PASS`. A STANDARD `PASS` without a reproduction records that the
regression test is the reproduction it lacks. Otherwise, one more bounded
investigation (`RETRY`) aimed at the missing item, then the specialist.

Go straight to the specialist when the bug is COMPLEX, an alternative that
would change the fix is still live, an intermittent failure was not
reproduced, or a fix attempt already failed.

## Specialist grading

<!-- aitk-model-route:debug.rca-specialist -->
Launch one fresh RCA specialist worker on `rca` (default) or `deep-rca`
(competing causes still live after an `rca` pass, intermittent or
history-dependent failures, or cross-system behavior). Prefer the other
provider. The prompt carries the symptom in code-level terms, the evidence
gathered, the RCA record so far with the alternatives considered and the
proposed regression check, and whether the specialist is validating or
producing the RCA. The worker receives its contract inline from the route
runner and returns `Verdict: PASS | REVISE | ESCALATE`.

## Consume the verdict

- `PASS` → gate `PASS`; the root cause and regression check go into
  `PROJECT.md`, and planning starts.
- `REVISE` → close the named gaps once (parent or debugger worker), then
  re-validate once.
- `ESCALATE` → `deep-rca` if not yet used; otherwise `USER_DECISION` with the
  fact or environment access the specialist named.

Record with `bin/aitk project-state gate --gate rca --status <...> --unit rca`.
Two failed implementation attempts or a materially changed RCA reopen this
gate; that is the rabbit-hole guardrail.
