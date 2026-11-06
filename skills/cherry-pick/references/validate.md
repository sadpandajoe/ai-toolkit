# Validate a Cherry

## Scope audit

Every cherry, clean applies included (they still ship adjacent-commit code,
[gotchas.md](../gotchas.md) #1):

```bash
<skill-dir>/scripts/scope-audit.sh <source-commit>      # -C <repo> for another checkout
```

It compares the exact changed lines of the source commit and the result, file
by file, and lists extra files and lines (with the source-side commits behind
them), missing lines (an adaptation or an incomplete pick), and lines a move or
copy carried from a neighbouring commit. Extra and moved lines are leaks until
proven otherwise; each missing line must match an adaptation you made.

No findings and no conflicts resolved: the audit is `CLEAN`. Otherwise get a
fresh, independent read (the `reviewer` agent) with the source SHA, the target
SHA, the literal script output and your adaptation summary. It compares `git
diff <source>^..<source>` with `git diff HEAD^..HEAD` hunk by hunk, traces each
extra hunk with `git log --oneline <source-branch> -S "<line>" -- <file>`, and
returns the script output verbatim, a per-hunk origin verdict, and `CLEAN`,
`LEAK — revert <hunks>` or an escalation. Revert named leaks, amend, and audit
the amended commit again. A leak that looks like a required prerequisite goes
to the user. Record `CLEAN`, `LEAKED-REVERTED` or `ESCALATED`.

## Correctness

Run pre-commit **after** the cherry commit exists and **before** pushing:
`pre-commit run --files <changed files>`. Extra indentation from the target's
nesting trips line-length lint even when tests pass
([gotchas.md](../gotchas.md) #4). Amend fixes into the in-progress cherry
(`git commit --amend --no-edit`) and re-run until clean. Failures in files the
pick did not touch are noted, not fixed.

## Validation labels

The only vocabulary; don't overstate:

| Label | Meaning |
|-------|---------|
| **Tested** | Build + targeted tests passed |
| **Checked** | Lint/type-check passed, no targeted tests run |
| **Build-only** | Build (or pre-commit) passed, nothing beyond |
| **Structural** | Markers clear, file parses, nothing run |
| **Not run** | No validation |

Never "Clean" or "Validated". When runnable targeted tests did not run, say
which, why, and "run before merging".

## Dependency manifests

A pick touching `package.json`, a lockfile, `requirements.txt`, `setup.py` or
`pyproject.toml` is not routine: prefer the repo's build or CI commands over a
local reinstall, and treat any rebuild or environment refresh as a question for
the user. For pip-compiled `requirements.txt`, resolve the source `.in` file
first, then offer regenerating with `pip-compile` or resolving surgically. A
different package manager or lockfile on the target is a stop.
