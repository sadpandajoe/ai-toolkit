# Fix CI Failures

> **When**: A CI build failed and you want it diagnosed, fixed where safe, verified, and pushed under the default authorization.
> **Produces**: Evidence-based classification, `PROJECT.md` triage and completion entries, scoped fixes, verification, a review gate, and a commit action or a clear hold.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

`fix-ci` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`.

## Usage

```
fix-ci <run-url> | <pr-number> | <log-file> | <zip-file> | (none: latest failed run on this branch)
fix-ci <target> --gate-strict    # WEAK verification is BLOCKED even when CI would verify downstream
fix-ci <target> --no-pr          # commit and push only; skip the draft PR
```

## Goal Loop

1. **Gather logs** with `debug/references/ci-gather-logs.md`. Enumerate the
   full check rollup first; external CI never appears in `gh run list`
   (`rules/ci-evidence.md`). Stop after the first auth failure on external CI
   and ask for a log excerpt. No resolvable log output or artifact source is
   `BLOCKED`: never reason from a dashboard, a run title, or a check name.
   Large logs go to the toolkit's debugger agent, which extracts the failing
   lines, never to the parent.
   <!-- aitk-model-route:debug.ci-triage -->
   Launch a triage worker on `rca` (or `deep-rca`) only when a novel failure
   pattern needs isolated diagnosis or independent failures need parallel
   analysis; it returns the compact classification record.
2. **Classify and group** with `debug/references/ci-classify-failure.md` and
   `debug/references/ci-fix-orchestration.md`. Write the initial triage to
   `PROJECT.md` before branching (hard gate): failing run, failures,
   ours/pre-existing split, hypothesis each. All pre-existing → exit with
   evidence, no fix cycle.
3. **Classify complexity** per `rules/complexity-gate.md` and
   persist with `bin/aitk project-state init --workflow fix-ci ... --format
   block`; paste the Complexity Gate it prints.
4. **Diagnose.** The parent diagnoses known patterns. The independent RCA
   specialist (`debug/references/review-rca.md`) enters only for CI-only
   failures that do not reproduce locally, flakiness or races, or a failure
   that survived one fix attempt. Record each outcome with `bin/aitk
   project-state gate --gate rca --unit ci-rca`.
5. **Fix** the selected path only, scoped to the failing surface. Use
   `CI_FIX.md` (`debug/templates/ci-fix-manifest.md`) for three or more failed
   jobs or artifact bundles.
6. **Verify** with `skills/verification-loop/SKILL.md`, starting with the
   command closest to the failing CI step, then nearby checks on the changed
   files, and record the strength with `bin/aitk verify --run "<cmd>"
   --strength <STRONG | PARTIAL | WEAK>` per the table in `rules/gates.md`.
   When the failing check cannot run locally, CI is the downstream verifier: `PASS (downstream: CI)` is legitimate for `PARTIAL`,
   and for `WEAK` unless `--gate-strict`; a push after a locally failed check
   never is.
7. **Review** changed repo-tracked files through `review-code`; the review
   exception in `rules/gates.md` covers zero-logic and micro fixes. Record the
   outcome with `bin/aitk project-state gate --gate review --result
   <envelope>` (`--exception zero-logic|micro-fix` for an exception) and paste
   the block it prints.
8. **Commit action.** `STRONG` verification, review gate `PASS`, and the
   current feature branch on the expected remote (never `main`) → deliver
   before any `project-state advance`. Amend, rebase, force-push, an ambiguous
   push target, `PARTIAL` or `WEAK` verification (a downstream `PASS` is never
   `STRONG`), or a COMPLEX hold → present the diagnosis and stop. Detect a
   cherry-pick flow before recommending an amend target. In order:
   1. `--no-pr`: commit and push per step 2, then stop, recording
      `pushed — awaiting PR request`.
   2. Create a new commit and push it. When the branch
      already has an upstream, require
      `git rev-parse --abbrev-ref "<branch>@{upstream}"` to equal
      `<remote>/<branch>` (the upstream's own remote), else pause (ambiguous
      push target); then push with
      `git push "<remote>" "HEAD:refs/heads/<branch>"` (never a bare `git push`,
      never `-u`). With no upstream, run `git push -u <remote> HEAD` (`<remote>` is
      `branch.<name>.pushRemote`, else `remote.pushDefault`, else `origin`;
      pause on an ambiguous push target).
   3. Run `create-pr --draft`. `## PR Exists` records
      `PR #n (existing, draft|ready)` (from its `Draft:` value) with no
      reservation; `## PR Not Opened` records its `pushed — awaiting PR request
      (<reason>)` line.
   4. On `## PR Ready`, run `bin/aitk checkpoint reserve --workflow fix-ci --key
      published_pr --operation-id phase:<name>` (`phase:single` for a
      SINGLE_PHASE fix), resume `create-pr` at its step 7, then `bin/aitk
      checkpoint apply --workflow fix-ci --key published_pr --operation-id
      phase:<name> --result-digest sha256:<sha256 of the PR URL>`, and finish
      `create-pr` steps 8-9.

   The PR is a draft only; promotion, reviewers, and merge need the user's
   words.
9. **Finish.** Append the `Completed` entry to `PROJECT.md` (hard gate),
   summarize as `## Fix-CI Complete` (what failed, the fix, verification
   strength, review status, open risks, next action), and record
   metrics with `bin/aitk metrics emit --workflow fix-ci --status <status>
   --workers <route>=<n> …` (complexity, gates, and retries come from the
   snapshot).

## Intervention points

External dependency or environment block, or a scope or product choice.
