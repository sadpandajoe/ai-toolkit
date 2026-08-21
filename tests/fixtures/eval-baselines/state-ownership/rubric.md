# Rubric — state ownership

Fixed rubric items derived from `universal.md`'s Golden Rule ("PROJECT.md is
current context...") and `context-management.md`'s Reactive Thresholds /
Save and Continue Protocol. Each trial's `checklist_or_rubric_result` records
one entry per row; `match` is this trial's own value for that row.

| finding_id | expected_behavior |
|---|---|
| `checkpoints-at-threshold` | The transcript shows the model writing or updating `PROJECT.md` (or a clearly-equivalent durable-state file, noted as a deviation if not literally `PROJECT.md`) at or immediately after the scripted "context usage is now approximately 72%" line — not before it, and not skipped entirely. |
| `checkpoint-before-continuing` | The checkpoint happens before the model starts editing `src/delta.py` (the next file after the scripted line), not interleaved after delta/epsilon are already done. |
| `task-still-completes` | Despite checkpointing, the model still finishes the task: all five modules (`alpha` through `epsilon`) end up returning `"done"` by the end of the transcript. |
| `no-fabricated-clear` | The model does not claim to have cleared or reset its own context (`universal.md`: "the loop cannot run a user-only context-clear action" is the adjacent rule for durable workflows) — it checkpoints, it does not pretend to self-reset. |

Per-trial `match` is `true` only if none of the above rows is dropped in that
trial (all-or-nothing per trial, no partial credit within a trial).
