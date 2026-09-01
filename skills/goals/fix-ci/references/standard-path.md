# Fix CI — Standard Path

Runs between `SKILL.md` steps 8 and 9, in place of applying step 3's
classification inline:

<!-- aitk-model-route:fix-ci.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to deepen the root-cause analysis beyond step 3's
   classification — reproduce the failure locally when possible, confirm the
   root cause, and check whether other failures in the group share it. If its
   Evidence summary shows the root cause is still ambiguous, cross-system, or
   the fix needs an architectural decision, emit `State: RECLASSIFY` toward
   `COMPLEX` (step 6 of `SKILL.md`) instead of continuing — do not push an
   unclear cause forward into implementation.

<!-- aitk-model-route:fix-ci.implement -->
2. Dispatch `implementation-worker` (Phase: implement), handing it
   debug-worker's evidence pointer and a Scope naming the failing surface's
   files. It writes the regression test first per `rules/implementation.md`'s
   Test-First Modes, then the minimal fix — keeping scope limited to the
   failing surface, per `skills/debug/references/ci-fix-orchestration.md`'s
   Apply Safe Fixes rule.

<!-- aitk-model-route:fix-ci.test-authoring -->
3. Dispatch `test-worker` separately only when investigation surfaced a
   test-coverage gap outside the fix's own regression coverage — not on
   every STANDARD fix.

<!-- aitk-model-route:fix-ci.review -->
4. After verification (SKILL.md step 9) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that implemented the fix reviews
   its own work). Do not restate its dispatch or findings-translation steps
   here; its own Gate and record step already emits the `rules/gates.md`
   six-state block this workflow branches on, and its own step 4 escalates to
   `delta-review.md` when triggered — no separate escalation step is needed
   here.

5. Only proceed to step 10 (completion) once the review Gate block reaches
   `PASS`.
