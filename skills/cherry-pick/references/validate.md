# Validate a Cherry

## Scope audit

```bash
<skill-dir>/scripts/scope-audit.sh <source-commit>      # -C <repo> for another checkout
```

Every cherry, clean applies included ([gotchas.md](../gotchas.md) #1). The
script's header describes its report. Extra and moved lines are leaks until
proven otherwise; each missing line must match an adaptation you made.

Exit 0 with no conflicts resolved is `CLEAN`. Otherwise get an independent
read from the `reviewer` agent. It knows nothing of this audit, so its prompt
carries the source SHA, the target SHA, the script output verbatim, your
adaptation summary, and the ask: compare `git diff <source>^..<source>` with
`git diff HEAD^..HEAD` hunk by hunk, trace each extra hunk with `git log
--oneline <source-branch> -S "<line>" -- <file>`, and return the script output
verbatim, a per-hunk origin verdict, and `CLEAN`, `LEAK — revert <hunks>` or an
escalation. Revert named leaks, amend, and audit the amended commit again. A
leak that looks like a required prerequisite goes to the user. Record `CLEAN`,
`LEAKED-REVERTED` or `ESCALATED`.

## Before the push

`pre-commit run --files <changed files>` once the cherry commit exists, amending
fixes into the in-progress cherry until clean ([gotchas.md](../gotchas.md) #4).
Failures in files the pick did not touch are noted, not fixed.

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
`pyproject.toml`: use the repo's build or CI commands rather than a local
reinstall, and ask before any rebuild or environment refresh. A pip-compiled
`requirements.txt` resolves from its `.in` file first; then offer
`pip-compile` or a surgical resolution. A different package manager or
lockfile on the target is a stop.
