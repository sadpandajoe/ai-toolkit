---
tier: Heavy
---

# Review Code Quality

Use this phase when repo-tracked files have changed and need a code quality review/fix loop. Works for both local changes (`review-code`) and PR reviews (`review-pr`).

## Required Context
Read before starting: `rules/code-review.md`, `rules/review-gate.md`, `rules/stop-rules.md`
Findings use severity tags from `rules/severity.md` and scoring from `rules/code-review.md`.

## Goal

Wrap the available code-review mechanism in a repo-standard loop:

- scope the review to the changed files or requested path
- normalize findings against `rules/code-review.md`
- fix actionable issues
- verify the fixes
- re-run review until only nitpicks or user decisions remain

## Modes

This reference is read in two different roles. Obey the one you are in — the
step list below is split accordingly.

| Mode | Who runs it | Steps | Allowed effects |
|------|-------------|-------|-----------------|
| **Lens mode** | A routed review worker (`review`/`deep-review`) | 1–6, 10 | Read-only. Report findings; do not edit files, run tests, or dispatch anything. |
| **Orchestrator mode** | The main thread of `review-code` / `review-pr` | 7–9 | Applies fixes, re-runs checks, dispatches the final pass. |

<!-- aitk-model-route-exempt:describes-worker-tool-boundary -->
The runtime dispatches lens work to routed, read-only review workers, so steps
7–9 are mechanically impossible in lens mode. If you are a routed worker, stop
after steps 1–6 and 10 and return findings; never report a fix you could not
apply as if it were applied.

## Process

### Lens mode — findings (steps 1–6, 10)

1. Gather the changed files:
   - **Uncommitted mode** (default): unstaged and staged diffs.
   - **Committed mode** (`--committed` or when invoked on already-committed changes): `git diff <base>..HEAD`. Skip stage/commit steps in the calling workflow.
   - Apply any explicit path filtering.
2. Perform a code review using the criteria in `rules/code-review.md`. Read each changed file, examine the diff, and assess against the scoring framework and severity tags.
3. **DRY + modeling check.** For any new helper, utility, or non-trivial logic introduced in the diff:
   - Check the dependency manifest (`package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, etc.) for a library that already provides this. Flag reimplementations of installed packages as `[minor]` (or `[major]` if the reimplementation has bugs the library has already fixed).
   - Grep the repo for sibling implementations of the same logic. Flag duplication and propose extraction or reuse.
   - **Reuse over rewrite**: for any new function, ask whether an existing function in the repo or an installed dependency could have been called, wrapped, or extended instead. Flag fresh implementations of partially-overlapping logic as `[minor]` even when there's no exact duplication — composition is preferred over parallel implementations that drift over time.
   - Verify placement: is this logic in the module/package/class where a future reader would look for it, with a signature that matches its neighbors? Misplaced or oddly-shaped code is `[minor]` even if it's correct in isolation.
4. Classify findings as `[major]`, `[minor]`, or `[nitpick]`.
5. For bug-fix reviews: grep the codebase for the same pattern that caused the bug (e.g., if the fix changed `e.target` to `e.currentTarget`, search for other occurrences of the broken pattern). Report matches as findings.
6. **Check test coverage for changed behavior.** For each changed file that introduces or modifies behavior, verify that a corresponding test exists. Missing tests are a `[major]` finding. This applies to the original diff **and** to any fixes made during this review loop — if you fix code in step 7, that fix also needs test coverage. Exception: if the test gap is explicitly tracked as a follow-up in PROJECT.md with a clear plan and owner, note it in the summary's Remaining section instead of classifying it as a finding.
   - **No tests found for changed logic**: After flagging as `[major]`, record that the test-plan lens (`testing/references/review-testplan.md`) is needed. In lens mode this is a request in your output; the orchestrator owns the dispatch.
   - **Tests found**: Record that the test-quality lens (`testing/references/review-tests.md`) is needed to evaluate whether they catch regressions, plus test suggestions for additional coverage.

10. **Pre-verdict claim check.** Before reporting "clean", name one claim the verdict rests on that the diff alone doesn't prove, and verify it with a cheap check: does the title/commit message match what changed; do docs or call sites still reference a surface this change removed; does a changed pin/version resolve to what's claimed; is anything that referenced a deleted symbol now dangling. State the check and its result. If the diff is self-contained, say so — don't skip the question. Apply the finding calibration in `rules/code-review.md` (scope-before-correctness, symmetry cap, convergent vs single-source) when grading what surfaces.

### Orchestrator mode — fix loop (steps 7–9)

Only the main thread runs these.

7. Fix all `[major]` and `[minor]` items directly — including adding tests for uncovered behavior.
8. Re-run targeted tests after each fix to catch regressions.
<!-- aitk-model-route:review.code-quality-final -->
9. Dispatch a fresh-context reviewer for the changed files — including files
   fixed and tests added during this loop. The main thread may synthesize and
   apply findings, but it must not substitute self-review for this final pass.
   Use `review` for a bounded pass and `deep-review` when the integrated diff is
   cross-system, security-sensitive, adversarial, or otherwise high-risk. Check
   error paths, async ordering, state consistency, and boundary conditions.
   Prefer a model family that did not raise the findings being re-checked, per
   [ensemble.md](ensemble.md).

## Stop Rules

Apply stop rules from `rules/stop-rules.md`.

## Notes

- Test-gap checks stay scoped to the changed files; broader scenario discovery belongs to the `qa` support workflows, not `review-code`.
- If a fix causes a regression, revert that fix and surface the trade-off instead of shipping it.
