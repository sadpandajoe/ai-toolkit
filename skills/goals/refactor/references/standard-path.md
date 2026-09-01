# Refactor — Standard Path

Runs between `SKILL.md` steps 5 and 6, in place of inline refactoring:

<!-- aitk-model-route:refactor.invariants -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to establish the invariants this refactor must preserve:
   the existing tests, contracts, or observable behavior that must read
   identically before and after. If no existing test coverage exercises the
   scope, its Evidence summary must say so explicitly — that gap becomes a
   `required_criteria` entry for step 6's verification (write the missing
   characterization test first, then refactor), not a silent assumption. If
   the scope's current behavior is itself ambiguous or contested, emit
   `State: RECLASSIFY` toward `COMPLEX` (step 3 of `SKILL.md`) instead of
   continuing — do not refactor against an invariant nobody actually agreed
   to.

2. Check the invariant evidence against a minimal checklist — behavior
   named, existing coverage identified (or its absence flagged), scope
   boundary named — and emit its Gate block explicitly, under gate name
   `refactor-invariants`: all three items evidenced is `PASS`; a missing
   item is `RETRY` (re-dispatch step 1 with the gap named); the same item
   still missing on the next attempt is `ESCALATE` per `rules/gates.md`'s
   Repeat-Failure Counting Rule. Do not start step 3 before this gate
   reaches `PASS`.

<!-- aitk-model-route:refactor.implement -->
3. Dispatch `implementation-worker` (Phase: implement), handing it the
   invariant evidence pointer and a Scope naming the files the refactor may
   touch. It performs the restructuring without changing the invariants'
   observable behavior — no new features, no bug fixes folded in, per
   `rules/implementation.md`.

<!-- aitk-model-route:refactor.review -->
4. After verification (SKILL.md step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that performed the refactor
   reviews its own work). Do not restate its dispatch or findings-
   translation steps here; its own Gate and record step already emits the
   `rules/gates.md` six-state block this workflow branches on, and its own
   step 4 escalates to `delta-review.md` when triggered — no separate
   escalation step is needed here.

5. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.
