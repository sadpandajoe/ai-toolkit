# Checklist — workflows.watch-pr-poll

Derived directly from `evidence/checks.json` and `evidence/comments.json`
(not from any trial's own output). A trial's `checklist_or_rubric_result`
records `match: true` for a required item only if the corresponding fact
appears in that trial's delta report. Additional findings beyond this list
never count against `match` (recall grading, not exact-match).

| finding_id | expected |
|---|---|
| `failed-run-id` | Delta report names run id `90210` as newly failed. |
| `failed-run-job` | Delta report names the job `pytest-unit`. |
| `failed-run-error` | Delta report includes the error line (or a faithful summary of it) — `AssertionError: expected delay <= 30.0, got 47.5` on `test_backoff_caps_at_max_delay`. |
| `new-thread-id` | Delta report names thread id `PRRT_kwDOAexample0002` as new since the cursor. |
| `no-spurious-first-thread` | Delta report does not present `PRRT_kwDOAexample0001` as new (it was already resolved before the previous poll — `new_since_cursor: false`). |
| `no-spurious-passing-checks` | Delta report does not present `lint` (run `90211`) or `typecheck` (run `90212`) as failed or changed — both were `success` in both the previous and current poll. |
