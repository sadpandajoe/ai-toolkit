# Observations

Append-only, local, high-signal: `.ai-toolkit/observations.jsonl`. One JSON
object per line, written by the orchestrator at the moment a trigger fires, and
never read back during normal engineering. Reviewing the queue is a separate,
deliberate step.

## Triggers (write exactly these)

| Trigger | `kind` | Why it is worth a line |
|---|---|---|
| User corrects a decision, routing, or output | `user-correction` | Direct evidence a skill, rule, or routing assumption is wrong |
| Skill misroute or manual override of the selected workflow | `misroute` | Becomes a routing regression case |
| Reclassification (complexity, size, or shape moved) | `reclassify` | Calibrates the classifier |
| Same gate fails twice for the same reason | `gate-repeat` | Shows a missing capability or escalation rule |
| A specialist invalidates an RCA or plan assumption | `specialist-invalidation` | High-value reasoning failure |
| A manual workaround repeated in the same or another session | `workaround` | Candidate for a reusable skill |
| A review lane crossed a yield threshold and was demoted (`rules/code-review.md`, Yield Thresholds) | `low-yield-lane` | Candidate for a durable trigger change or removal; `reflect` restores or retires it |

Do not log routine progress, successful gates, or opinions.

## Line shape

```json
{"timestamp":"<ISO 8601>","kind":"reclassify","workflow":"fix-bug","phase":"implement","complexity":"STANDARD->COMPLEX","size":"M","shape":"SINGLE_PHASE","detail":"second failed fix attempt exposed a concurrency path","evidence":"PROJECT.md#gate-verification-2","eval_candidate":true}
```

Fields other than `timestamp`, `kind`, `workflow`, and `detail` are optional.
Keep `detail` to one sentence and free of PII.

## Review (`reflect observations`)

Nothing else reads this queue. `complete-project` runs this review before it
scans memories, `start` suggests it at 10 or more unreviewed lines, and the
Stop hook `hooks/observation-reminder.sh` prints the same reminder; the review
itself is always a deliberate, confirmed step.

1. Run `bin/aitk lane-yield` and read its demotions alongside the queue: it
   applies the yield table in `rules/code-review.md` to `review.lanes` in
   `.ai-toolkit/metrics.jsonl`, so a lane proposal carries its numbers.
2. Read the queue; group lines by `kind` and by the skill or rule they
   implicate.
3. For each cluster of two or more, propose one change: a rule wording fix, a
   skill checklist addition, a classifier signal, or a lane removal. Cite the
   lines.
4. Write an eval candidate for each proposal under `evals/<family>/` as a
   JSONL case (`input`, `expected`, `source: observation`), so the regression
   becomes detectable.
5. Present proposals; apply only on confirmation
   (`references/rule-promotion.md`). Move reviewed lines to
   `.ai-toolkit/observations.reviewed.jsonl`.

Metrics that pair with this queue live in `.ai-toolkit/metrics.jsonl`:
gate retries and escalations, reclassification rate, accepted versus rejected
findings, delta-review yield, premium-model share by phase.
