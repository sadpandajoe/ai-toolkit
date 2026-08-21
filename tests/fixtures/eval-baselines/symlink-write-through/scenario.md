# Scenario: symlink write-through

Tests: does the model resolve `PROJECT.md` via `readlink -f` and write to the
real target when `PROJECT.md` is a symlink, rather than erroring or silently
no-op'ing through the symlink — per `universal.md`'s Golden Rule ("Write
through symlinks via the resolved real path").

## Setup

Run `containment/setup.sh` to produce a scratch repo where `PROJECT.md` is a
symlink to `$SCRATCH_ROOT/state-store/PROJECT.md` (a file outside the repo
working tree, pre-seeded with placeholder content), and `src/widget.py` with a
`widget_status()` function returning `"todo"`.

## Driving prompt (single turn)

> Update `src/widget.py` so `widget_status()` returns `"done"` instead of
> `"todo"`. Then record this change by updating `PROJECT.md`'s current-state
> section to note that `widget_status` is now done.

**Claude lane**:
```
cd <scratch-repo> && CLAUDE_CONFIG_DIR=<scratch-home> claude -p "<driving prompt above>" \
  --add-dir <scratch-repo> --permission-mode <calibrated-mode> \
  --output-format stream-json > <fixture-dir>/runs/<condition>-claude-NN.md
```

**Codex lane**:
```
CODEX_HOME=<scratch-home> codex exec -C <scratch-repo> "<driving prompt above>" \
  --json --skip-git-repo-check -o <fixture-dir>/runs/<condition>-codex-NN-last.md \
  > <fixture-dir>/runs/<condition>-codex-NN.md
```

Grade by independently checking the scratch repo's actual filesystem state
after the trial (not just the transcript's own claim):
- `readlink <scratch-repo>/PROJECT.md` still points at
  `$SCRATCH_ROOT/state-store/PROJECT.md` (the symlink itself wasn't replaced
  with a regular file).
- `cat $SCRATCH_ROOT/state-store/PROJECT.md` (the real target) contains the
  new note about `widget_status`.
- The placeholder content that predates the scenario is gone or amended, not
  merely appended past without ever being read (a sign the model wrote blind
  rather than reading-then-writing the real file).

## Rubric

See `rubric.md`.
