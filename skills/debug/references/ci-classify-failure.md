# Classify CI Failure

Use this phase after CI logs or artifacts have been gathered.

## Goal

Identify the failing step, match it to a known pattern when possible, and produce a root-cause hypothesis plus a narrow proposed fix.

## Known Failure Patterns

| Pattern | Symptoms | Fix | Confidence |
|---------|----------|-----|------------|
| **Lint/format drift** | `eslint` or `prettier` failures on lines you didn't change | Run formatter (`npm run lint:fix`, `ruff format`); recommend commit only after authorization | HIGH |
| **Flaky test — timing** | Test passes locally, fails in CI with timeout | Replace fixed sleeps and timeouts with a wait on the condition the test needs; after two independent test-layer hardenings miss the same flake family, look at infrastructure instead (`skills/debug/lessons.md`) | MEDIUM |
| **Flaky test — order-dependent** | Test fails only when run with full suite, passes alone | Find shared state (global, DB, env var), isolate it | MEDIUM |
| **Cherry-pick residue** | Conflict markers (`<<<<<<<`) in committed files | Search and resolve remaining markers | HIGH |
| **Lock file conflict** | `npm ci` fails with lockfile mismatch | Regenerate lockfile: `npm install`; recommend committing `package-lock.json` only after authorization | HIGH |
| **Pre-existing / not-our-failure** | Failing file/test is not in our diff; same failure exists on the base branch | N/A — not caused by this branch | HIGH |
| **Transient infra** | 401/5xx/timeout from GitHub, a registry, or the network during an infra step (checkout, auth, artifact up/download, runner setup) — not in the code under test; no correlation with the diff; same step passed on a previous run | Re-run failed jobs (`gh run rerun --failed`) before any diagnosis; cap 2 reruns, then treat as real | HIGH after one clean re-run |

## Classifying a Failure

Treat each failing job or step (build, test, lint, install, or workflow config)
as its own failure unit, collapse repeated stack traces, and match each unit to
a pattern above when one fits; when none does, read the referenced files and
recent commits before calling it novel. Two checks decide whether a failure is
ours:

- **Ownership.** A failure is **Pre-existing / not-our-failure** only when the
  failing file or test is outside our diff (`git diff --name-only <base>...HEAD`)
  *and* the same failure exists on the base branch. Check the base tip's
  **full** rollup, not just Actions — an external-CI failure on base is
  invisible to `gh run list` (see `rules/ci-evidence.md`):
  ```bash
  gh api repos/{owner}/{repo}/commits/<base-sha>/check-runs --jq '.check_runs[] | select(.conclusion == "failure") | .name'
  gh api repos/{owner}/{repo}/commits/<base-sha>/status --jq '.statuses[] | select(.state == "failure" or .state == "error") | .context'
  ```
- **Auth failures.** A **401** on a step that normally authenticates fine is a
  transient token blip — re-run before diagnosing. A **403** with a stable
  identity is a real permissions problem. Do not ship a permissions fix for a
  401, and do not classify either as ours without checking whether the step
  touches our diff at all.

Use numeric confidence with these defaults:
- `8-10` = `HIGH`
- `5-7` = `MEDIUM`
- `1-4` = `LOW`

## Output Format

For each failure, end with this block:

```markdown
### Failure: [step name]

**Error**: [key error message]
**Pattern**: [matched pattern name, or "Novel"]
**Confidence**: X/10 (`HIGH` / `MEDIUM` / `LOW`)
**Root Cause**: [explanation]
**Proposed Fix**: [specific fix with commands/code changes]
**Verification**: [how to verify the fix locally]
```

For **Pre-existing / not-our-failure** classifications, set `Proposed Fix: N/A` and `Verification: N/A`. The calling workflow handles the early-exit path.

The calling workflow grades this output with `rules/gates.md` and the Complexity Gate to decide whether to proceed automatically.
