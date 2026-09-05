# RCA Gate

The RCA gate decides whether a root-cause story is evidenced enough to plan a
fix. The parent grades STANDARD bugs itself; an independent specialist grades
COMPLEX or uncertain ones.

## Evidence checklist

`PASS` requires every item evidenced, not asserted:

1. The failure mechanism is explained, not merely correlated.
2. Evidence points to the relevant execution or data path.
3. Competing likely causes were considered or ruled out.
4. The proposed fix changes the causal point, not only a visible symptom.
5. A verification strategy exists that could disprove the RCA.
6. For a bug fix, regression evidence fails before and passes after when
   feasible; otherwise the reason is recorded.

## Confidence calibration

The confidence number means one thing everywhere:

| Confidence | Meaning |
|---|---|
| 9-10 | Root cause reproduced locally; the fix is narrow and behavior-preserving |
| 7-8 | Root cause strongly evidenced but not directly reproduced; the fix is targeted |
| 5-6 | Root cause plausible but alternatives are still live; fix scope may move |
| 3-4 | Several plausible root causes; investigation incomplete |
| 1-2 | Root cause unknown; evidence indirect or contradictory |

## Parent grading (STANDARD)

Grade the investigation handoff against the checklist. Confidence 8/10 or
higher with every item evidenced → `PASS`. Below that, one more bounded
investigation (`RETRY`), then escalate to the specialist. A `PASS` at 8 is an
evidenced story without a reproduction; record that the regression test is the
reproduction it lacks.

## Specialist grading (COMPLEX, uncertain, or after a failed attempt)

<!-- aitk-model-route:debug.rca-specialist -->
Launch one fresh RCA specialist worker on `rca` (default) or `deep-rca`
(competing causes still live after an `rca` pass, intermittent or
history-dependent failures, or cross-system behavior). Prefer the other
provider. The prompt carries the symptom in code-level terms, the evidence
gathered, the current hypothesis and confidence, the alternatives considered,
the proposed regression check, and whether the specialist is validating or
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
