# Cherry-Pick Validate

Use after a cherry-pick applies cleanly or after conflict resolution. Prove the
moved change contains only the intended changes and left the target working.
Do not re-litigate whether the pick should have happened.

## Scope Audit

The parent runs the mechanical audit on every cherry, clean applies included:
they look fine and still ship adjacent-commit code ([../gotchas.md](../gotchas.md),
"Code from adjacent commits leaks").

```bash
<skill-dir>/scripts/scope-audit.sh <source-commit>      # -C <repo> for another checkout
```

It compares the exact changed lines of the source commit and the result, file
by file, and lists extra files and lines (with the source-side commits that
touched them), missing lines (an adaptation or an incomplete pick), and lines a
move or copy carried from a neighbouring commit. Extra and moved lines are
leaks until proven otherwise; each missing line must match an adaptation
recorded in adapt.

When the script reports nothing and no conflicts were resolved, the row's Scope
Audit is `CLEAN`. Otherwise run the LLM audit.

<!-- aitk-model-route:cherry-pick.validate-scope-leak -->
Spawn a fresh reviewer worker on `review` for the LLM audit, with the source SHA, the target SHA after apply, the literal script output and the adapt summary; re-run it on `deep-review` only when it returns ESCALATE.

The worker compares `git diff <source-commit>^..<source-commit>` with
`git diff HEAD^..HEAD` hunk by hunk, traces each extra hunk with
`git log --oneline --all -S "<line>" -- <file>`, and returns:

1. the literal `scope-audit.sh` output, pasted verbatim;
2. a per-hunk verdict: each extra hunk with its origin, or "none", and the
   legitimate adaptations (an import path for the target, a test for the
   picked change);
3. `CLEAN`, `LEAK — revert <hunks>` or `ESCALATE — <reason>`.

It does not run build or tests. The parent refuses `Applied` without all three.

<!-- aitk-model-route:cherry-pick.validate-scope-leak-rerun -->
On `LEAK`, the parent reverts the named hunks, amends, and sends the amended commit back to a fresh reviewer worker on the same route; loop until `CLEAN` or `ESCALATE`.

A leaked change that looks like a required prerequisite is escalated to the
user, never kept silently. Record `CLEAN`, `LEAKED-REVERTED` or `ESCALATED`.

## Correctness Validation

On the main thread, after the scope audit:

1. Confirm no conflict markers.
2. Run pre-commit on the changed files (below).
3. Run the smallest relevant build or type-check, discovered from
   `package.json`, `Makefile`, `pyproject.toml`, `setup.cfg` or CI config.
4. Run targeted tests for the changed area; broader validation when the pick
   touched shared infrastructure or the branches differ materially.

For config-only changes with nothing to build or test, parse the file and
assert the intended keys and values.

## Pre-Commit Gate

Run pre-commit on the changed files **after** the cherry-pick commit exists and
**before** pushing; clean applies have no `--continue` to hook into.

```bash
pre-commit run --files <changed-file-1> <changed-file-2>
# or the repo's equivalent CI lint/format command
```

The run's grant covers this local amend of the in-progress cherry and the
fast-forward push ([../SKILL.md](../SKILL.md), Authorization Boundary); never
amend older or pushed commits, rebase, or force-push. Auto-fixes and manual
fixes go in with `git add <files>` and `git commit --amend --no-edit`; re-run
until it passes. Failures on files the pick did not touch are noted, not fixed.
Order: validate → fix → amend → push → record the Push cell.

## Validation Status Labels

The only label table. Do not overstate:

| Label | Meaning |
|-------|---------|
| **Tested** | Build + targeted tests passed |
| **Checked** | Lint/type-check passed, no targeted tests run |
| **Build-only** | Build passed (pre-commit hooks or equivalent), no lint/type-check/test beyond that |
| **Structural** | Conflict markers clear, file parse OK, no lint/build/test run |
| **Not run** | No validation performed |

Never use "Clean" or "Validated"; they are ambiguous.

**Gap flagging.** When targeted tests existed and were runnable but did not
run, say which tests, why they were skipped, and the follow-up ("run before
merging"). Recording `Checked` or `Structural` when `Tested` was within reach
is an undercount to call out.

## Dependency Manifests

When the pick touches `package.json`, a lockfile, `requirements.txt`,
`setup.py` or `pyproject.toml`, validation is not routine: prefer the repo's
existing build, type-check or CI commands over a local reinstall, treat any
rebuild or environment refresh as an intervention point, and say when stronger
validation would need one. For pip-compiled `requirements.txt`, resolve the
source file first, then surface the choice between regenerating with
`pip-compile` and resolving surgically. A different package manager or
lockfile on the target is a stop.
