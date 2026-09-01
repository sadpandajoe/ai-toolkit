# Fix Bug — Standard Path

Runs between `SKILL.md` steps 5 and 6, in place of inline implementation.

<!-- aitk-model-route:fix-bug.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to reproduce the bug and identify root cause. If its Evidence
   summary shows the root cause is still ambiguous, cross-system, or the fix
   needs an architectural decision, emit `State: RECLASSIFY` toward `COMPLEX`
   (step 3 of `SKILL.md`) instead of continuing — do not push an unclear
   cause forward into implementation.

2. Check debug-worker's evidence against
   `skills/debug/references/review-rca.md`'s RCA Gate Evidence Checklist and
   emit its Gate block explicitly, under gate name `fix-bug-rca`: all six
   checklist items evidenced is `PASS`; a missing item is `RETRY` (re-dispatch
   step 1 with the gap named); the same item still missing on the next
   attempt is `ESCALATE` per `rules/gates.md`'s Repeat-Failure Counting Rule.
   Do not start step 3 before this gate reaches `PASS` — this is the explicit
   check the ambiguity language in step 1 only gestures at.

<!-- aitk-model-route:fix-bug.implement -->
3. Dispatch `implementation-worker` (Phase: implement), handing it
   debug-worker's evidence pointer and a Scope naming the files the fix may
   touch. It writes the regression test first per `rules/implementation.md`'s
   Test-First Modes, then the minimal fix.

<!-- aitk-model-route:fix-bug.test-authoring -->
4. Dispatch `test-worker` separately only when investigation surfaced a
   test-coverage gap outside the fix's own regression test — not on every
   STANDARD fix.

<!-- aitk-model-route:fix-bug.review -->
5. After verification (SKILL.md step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in
   full — Dispatch, Validate findings before fixing, Gate and record,
   Escalate only when triggered — with Scope: the resulting diff, Author
   identity: `implementation-worker` (never the worker that implemented the
   fix reviews its own work). Do not restate its dispatch or
   findings-translation steps here; its own Gate and record step already
   emits the `rules/gates.md` six-state block this workflow branches on, and
   its own step 4 escalates to `delta-review.md` when triggered — no
   separate escalation step is needed here.

6. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.
