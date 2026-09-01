# Create Feature — Standard Path

Runs between `SKILL.md` steps 5 and 6, in place of inline implementation.
Unlike `fix-bug`, there is no root-cause investigation phase — a feature
request starts from what the user described, not a symptom. Survey existing
patterns to follow inline, as the orchestrator (`rules/complexity-gate.md`'s
Standard Path already allows inline investigation/planning at this tier); no
specialist dispatch for the survey itself.

<!-- aitk-model-route:create-feature.implement -->
1. Dispatch `implementation-worker` per `rules/specialist-handoff.md` (Phase:
   implement), handing it the feature request, the surveyed pattern to
   follow, and a Scope naming the files it may touch. It writes tests first
   per `rules/implementation.md`'s Test-First Modes, then the feature code.

<!-- aitk-model-route:create-feature.test-authoring -->
2. Dispatch `test-worker` separately only when the feature needs coverage
   beyond the implementation worker's own tests (e.g. a new integration
   surface) — not on every `STANDARD` feature.

<!-- aitk-model-route:create-feature.review -->
3. After verification (SKILL.md step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that implemented the feature
   reviews its own work). Do not restate its dispatch or findings-translation
   steps here; its own Gate and record step already emits the
   `rules/gates.md` six-state block this workflow branches on, and its own
   step 4 escalates to `delta-review.md` when triggered — no separate
   escalation step is needed here.

4. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.
