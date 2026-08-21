# workflows.watch-pr-poll — evaluation prompt

This is a frozen, synthetic replay of the `workflows.watch-pr-poll` boundary
(`skills/workflows/references/watch-pr.md`, step 2.1). It exists only for the
Evaluation gate (PLAN.md) — no real PR, run, or comment data appears here.

## Task

You are the `operations` worker dispatched from `watch-pr`'s iteration loop.
The parent/tool layer has already polled the head SHA's check-run states and
comment threads since the last cursor. Reduce the supplied read-only evidence
below to a delta report: either `no change`, or the failed run id/job/error
lines plus any new thread ids. Do not review code, decide fixes, or take any
action beyond producing the delta report. Do not fetch anything — the evidence
below is the complete input.

## Evidence: check-run states

Previous poll's cursor (for comparison only — the failure/success delta is
between this and the current poll, not a live re-check):

```json
{
  "checks": [
    {"run_id": 90210, "job": "pytest-unit", "status": "in_progress", "conclusion": null},
    {"run_id": 90211, "job": "lint", "status": "completed", "conclusion": "success"},
    {"run_id": 90212, "job": "typecheck", "status": "completed", "conclusion": "success"}
  ]
}
```

Current poll:

```json
{
  "checks": [
    {"run_id": 90210, "job": "pytest-unit", "status": "completed", "conclusion": "failure", "error_summary": "tests/test_ingest_retry.py::test_backoff_caps_at_max_delay FAILED - AssertionError: expected delay <= 30.0, got 47.5"},
    {"run_id": 90211, "job": "lint", "status": "completed", "conclusion": "success"},
    {"run_id": 90212, "job": "typecheck", "status": "completed", "conclusion": "success"}
  ]
}
```

## Evidence: comment threads

Cursor: last thread seen before this poll was `PRRT_kwDOAexample0001`.

Current poll's threads:

```json
{
  "threads": [
    {
      "thread_id": "PRRT_kwDOAexample0001",
      "author": "review-bot",
      "body": "This thread was already resolved before the previous poll.",
      "resolved": true,
      "new_since_cursor": false
    },
    {
      "thread_id": "PRRT_kwDOAexample0002",
      "author": "sample-reviewer",
      "body": "Can the retry backoff cap be configurable instead of hardcoded to 30s?",
      "resolved": false,
      "new_since_cursor": true
    }
  ]
}
```

## Output

Produce the delta report only: which check run(s) newly failed (run id, job,
error line) since the previous poll, and which comment thread id(s) are new
since the cursor. Omit anything unchanged.
