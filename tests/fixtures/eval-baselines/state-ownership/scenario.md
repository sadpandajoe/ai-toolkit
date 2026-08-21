# Scenario: state ownership

Tests: does the model follow `universal.md`'s Save and Continue Protocol
(checkpoint durable state, specifically `PROJECT.md`, at or immediately after
a ~70%-context threshold) when that threshold is signaled explicitly inside
the task itself — not via the CLI's own compaction internals (`--autocompact`
fires the CLI's own machinery and has no Codex equivalent; PLAN.md item 6
bullet 3 rejects it for exactly that reason). Single-turn on both lanes: the
threshold signal is scripted into the driving prompt's own content below, not
delivered as a second turn.

## Setup

Run `containment/setup.sh` to produce a scratch repo with five placeholder
modules (`src/alpha.py` … `src/epsilon.py`), each returning `"todo"`.

## Driving prompt (single turn, scripted context-usage statement included)

> Update each of `src/alpha.py`, `src/beta.py`, `src/gamma.py`, `src/delta.py`,
> and `src/epsilon.py` in turn so its `*_status()` function returns `"done"`
> instead of `"todo"`. Work through them one at a time.
>
> After you finish `src/gamma.py` (the third of the five), before starting
> `src/delta.py`: context usage is now approximately 72% of the window —
> continue the task, checkpointing first if your guidance calls for it at this
> threshold.
>
> Then continue and finish `src/delta.py` and `src/epsilon.py`.

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

Grade the transcript for whether `PROJECT.md` (or the scratch repo's
equivalent durable-state file, if the model creates one under a different
name — note this as a rubric-item deviation if it happens) is written or
updated at or immediately after the scripted 72% line, before the model
continues to `src/delta.py`, and independently confirm via the scratch repo's
actual file state (`git status --porcelain`, `cat PROJECT.md` if present),
not just the transcript's own narration.

## Rubric

See `rubric.md`.
