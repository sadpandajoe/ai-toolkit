# Classify CI Failure

Use after CI logs or artifacts have been gathered. Identify the failing step,
match it to a known pattern when one fits, and produce a root-cause
hypothesis plus a narrow fix point.

## Known Failure Patterns

| Pattern | Symptoms | Action |
|---------|----------|--------|
| **Pre-existing / not-our-failure** | Failing file or test is not in our diff, and the same failure exists on the base branch | No fix; record the base-branch evidence |
| **Transient infra** | 5xx or timeout from GitHub, a registry, or the network during an infra step (checkout, auth, artifact transfer, runner setup); no correlation with the diff; the same step passed on a previous run | Rerun failed jobs (`gh run rerun --failed`) before any diagnosis; cap 2 reruns, then treat as real |
| **Auth 401 vs 403** | A **401** on a step that normally authenticates fine | Transient token blip: rerun as above. A **403** with a stable identity is a real permissions problem; never ship a permissions fix for a 401 |
| **Cherry-pick residue** | Conflict markers (`<<<<<<<`) in committed files | Resolve the remaining markers |
| **OOM** | Exit 137, `Killed`, or `JavaScript heap out of memory` | Resource, not code: lower the worker count or raise the job's memory before touching tests |
| **Flaky test** | Passes locally, fails in CI with a timeout, or fails only with the full suite | Wait on the condition instead of fixed sleeps, or isolate shared state; after two test-layer hardenings miss the same flake family, look at infrastructure ([lessons.md](../lessons.md)) |

## Classifying a Failure

Treat each failing job or step (build, test, lint, install, or workflow config)
as its own failure unit, collapse repeated stack traces, and match each unit to
a pattern above when one fits; when none does, read the referenced files and
recent commits before calling it novel.

A failure is **Pre-existing / not-our-failure** only when the failing file or
test is outside our diff (`git diff --name-only <base>...HEAD`) *and* the same
failure exists on the base branch. Check the base tip's **full** rollup, not
just Actions — an external-CI failure on base is invisible to `gh run list`
(see `rules/ci-evidence.md`):

```bash
gh api repos/{owner}/{repo}/commits/<base-sha>/check-runs --jq '.check_runs[] | select(.conclusion == "failure") | .name'
gh api repos/{owner}/{repo}/commits/<base-sha>/status --jq '.statuses[] | select(.state == "failure" or .state == "error") | .context'
```

Do not classify an auth failure as ours without checking whether the step
touches our diff at all.

## Output Format

For each failure, end with this block (the RCA record's field names from
`agents/specialists/rca.md`):

```markdown
### Failure: [step name]
Pattern: <matched pattern, or Novel>
Ours: yes | no — <base-branch evidence>
Problem: <key error message>
Root cause: <mechanism at file:line, or "not established">
Reproduced: yes — <local command> | no — <why>
Alternatives: ruled out — <cause: evidence> | live — <cause>
Fix point: <file:line, or N/A when not ours>
Regression check: <the local command closest to the failing CI step, or N/A>
```

The calling workflow grades this output with `rules/gates.md` and decides the
fix path and the commit action under its own grant.
