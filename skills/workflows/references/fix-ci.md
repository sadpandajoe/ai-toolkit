# Fix CI Failures

> **When**: A CI build failed and you want it diagnosed, fixed where safe, verified, and pushed under the default authorization.
> **Produces**: Evidence-based classification, `PROJECT.md` triage and completion entries, scoped fixes, verification, a review gate, and a commit action or a clear hold.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `fix-ci` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
fix-ci <run-url> | <pr-number> | <log-file> | <zip-file> | (none: latest failed run on this branch)
```

## Goal Loop

1. **Gather logs** with `debug/references/ci-gather-logs.md`. Enumerate the
   full check rollup first; external CI never appears in `gh run list`
   (`rules/ci-evidence.md`). Stop after the first auth failure on external CI
   and ask for a log excerpt. Large logs go to the toolkit's debugger agent,
   not the parent.
2. **Classify and group** with `debug/references/ci-classify-failure.md` and
   `debug/references/ci-fix-orchestration.md`. Write the initial triage to
   `PROJECT.md` before branching (hard gate): failing run, failures,
   ours/pre-existing split, hypothesis each. All pre-existing → exit with
   evidence, no fix cycle.
3. **Classify complexity** per the CI matrix in `ci-fix-orchestration.md` and
   persist with `bin/aitk project-state init --workflow fix-ci ...`.
4. **Diagnose.** The parent diagnoses known patterns. The independent RCA
   specialist (`debug/references/review-rca.md`) enters only for CI-only
   failures that do not reproduce locally, flakiness or races, or a failure
   that survived one fix attempt.
5. **Fix** the selected path only, scoped to the failing surface. Use
   `CI_FIX.md` (`debug/templates/ci-fix-manifest.md`) for three or more failed
   jobs or artifact bundles.
6. **Verify** with `skills/verification-loop/SKILL.md` using the verification
   strength tiers in `debug/references/ci-verify-fix.md`. When the failing
   check cannot run locally, CI is the downstream verifier: `PASS (downstream:
   CI)` is legitimate; a push after a locally failed check is not.
7. **Review** changed repo-tracked files through `review-code`; the review
   exception in `rules/gates.md` covers zero-logic and micro fixes.
8. **Commit action.** STRONG verification, review gate `PASS`, and the current
   feature branch on the expected remote → create a new commit and push.
   Amend, rebase, force-push, an ambiguous target, PARTIAL or WEAK
   verification, or a COMPLEX hold → present the diagnosis and stop. Detect a
   cherry-pick flow before recommending an amend target.
9. **Finish.** Append the `Completed` entry to `PROJECT.md` (hard gate),
   summarize with the shapes in `ci-fix-orchestration.md`, record
   `metrics-emit` with complexity, gate outcomes, retries, and worker usage.

## Intervention points

External dependency or environment block, or a scope or product choice.
