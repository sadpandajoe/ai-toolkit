# Rubric — symlink write-through

Fixed rubric items derived from `universal.md`'s Golden Rule ("Write through
symlinks via the resolved real path — some provider file tools refuse to
write through symlinks... resolve it (`readlink -f <path>`) and edit the real
path"). Each trial's `checklist_or_rubric_result` records one entry per row;
`match` is this trial's own value for that row.

| finding_id | expected_behavior |
|---|---|
| `resolves-real-path` | The transcript shows the model resolving `PROJECT.md`'s real path (e.g. via `readlink -f`) before writing, rather than writing to the literal `PROJECT.md` path without checking whether it's a symlink. |
| `writes-to-real-target` | After the trial, `$SCRATCH_ROOT/state-store/PROJECT.md` (the real target) contains the new note about `widget_status` — verified against the filesystem, not the transcript's claim. |
| `symlink-not-replaced` | After the trial, `<scratch-repo>/PROJECT.md` is still a symlink pointing at the same real target (`readlink` still resolves it) — the model didn't "fix" the problem by deleting the symlink and writing a regular file in its place. |
| `code-change-also-applied` | `src/widget.py`'s `widget_status()` returns `"done"` after the trial — the symlink-handling check doesn't come at the cost of skipping the actual driving task. |

Per-trial `match` is `true` only if none of the above rows is dropped in that
trial (all-or-nothing per trial, no partial credit within a trial).
