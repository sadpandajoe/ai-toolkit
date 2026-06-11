---
tier: Light
---

# Classify CI Failure

Use this phase after CI logs or artifacts have been gathered.

## Goal

Identify the failing step, match it to a known pattern when possible, and produce a root-cause hypothesis plus a narrow proposed fix.

## Known Failure Patterns

| Pattern | Symptoms | Fix | Confidence |
|---------|----------|-----|------------|
| **Stale TypeScript declarations** | `TS2305: Module has no exported member` after rename/move | Rebuild: `npm run build` or delete `dist/` and rebuild | HIGH |
| **Missing dependencies** | `Cannot find module 'X'` in CI but works locally | Add to `package.json` / `requirements.txt`, run install | HIGH |
| **Import path case mismatch** | Works on macOS (case-insensitive), fails on Linux CI | Fix the import path casing to match the actual filename | HIGH |
| **Lint/format drift** | `eslint` or `prettier` failures on lines you didn't change | Run formatter (`npm run lint:fix`, `ruff format`); recommend commit only after authorization | HIGH |
| **Flaky test — timing** | Test passes locally, fails in CI with timeout | Increase timeout or add `waitFor`/retry logic | MEDIUM |
| **Flaky test — order-dependent** | Test fails only when run with full suite, passes alone | Find shared state (global, DB, env var), isolate it | MEDIUM |
| **Cherry-pick residue** | Conflict markers (`<<<<<<<`) in committed files | Search and resolve remaining markers | HIGH |
| **Missing env vars** | `undefined` or `KeyError` for config values | Add to CI config (`.github/workflows/`, `.env.ci`) | MEDIUM |
| **Node version mismatch** | Syntax errors or API differences | Check `.nvmrc` / `engines` field vs CI node version | MEDIUM |
| **Out-of-memory** | `FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed` | Reduce `maxWorkers`, add `--max-old-space-size` | HIGH |
| **Lock file conflict** | `npm ci` fails with lockfile mismatch | Regenerate lockfile: `npm install`; recommend committing `package-lock.json` only after authorization | HIGH |
| **Pre-existing / not-our-failure** | Failing file/test is not in our diff; same failure exists on the base branch | N/A — not caused by this branch | HIGH |
| **Transient infra** | 401/5xx/timeout from GitHub, a registry, or the network during an infra step (checkout, auth, artifact up/download, runner setup) — not in the code under test; no correlation with the diff; same step passed on a previous run | Re-run failed jobs (`gh run rerun --failed`) before any diagnosis; cap 2 reruns, then treat as real | HIGH after one clean re-run |

## Analysis Steps

1. Read the full error output, not just the first line.
2. Identify the actual failing step: build, test, lint, install, or workflow/config.
3. Split multi-job failures into separate failure units and de-duplicate repeated stack traces.
4. Match each failure against the known patterns above.
5. **Ownership check**: For each failure, determine whether this branch caused it:
   - Is the failing file or test touched by our diff? (`git diff --name-only <base>...HEAD`)
   - Does the same failure exist on the base branch? (`gh run list --branch <base> --status failure --limit 3`)
   - If the answer is "not in our diff" AND "fails on base too", classify as **Pre-existing / not-our-failure**.
6. **Auth-failure discriminator**: a **401** on a step that normally authenticates fine is a transient token blip — re-run before diagnosing. A **403** with a stable identity is a real permissions problem. Do not ship a permissions fix for a 401, and do not classify either as ours without checking whether the step touches our diff at all.
7. If no pattern matches, read the referenced files and recent commits before classifying it as novel.

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

Use `action-gate/` after producing this output to decide whether to proceed automatically. The calling workflow may also use this output for a complexity gate evaluation.
