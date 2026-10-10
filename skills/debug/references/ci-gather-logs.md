# CI Gather Logs

Use at the start of `fix-ci` after input normalization. The goal is to resolve real failing log output before any classification happens.

## Inputs

Accepted sources:
- GitHub Actions run URL
- PR number
- local log file
- local zip artifact bundle
- no argument: latest failed run on current branch

## Enumerate All Failures First

See `rules/ci-evidence.md`. The merged check rollup is the **first** call, not a
fallback. `gh run list` and `gh pr checks` show GitHub Actions only — external CI
(Jenkins, Buildkite, CircleCI) posts commit *statuses*, which never appear there. A
single noisy Actions failure will otherwise look like the whole story.

```bash
gh pr view <number> --json statusCheckRollup,headRefName
```

With no PR, go via the commit — check-runs *and* statuses:

```bash
gh api repos/{owner}/{repo}/commits/{sha}/check-runs \
  --jq '.check_runs[] | select(.conclusion == "failure")'
gh api repos/{owner}/{repo}/commits/{sha}/status \
  --jq '.statuses[] | select(.state == "failure" or .state == "error")'
```

Enumerate every entry whose conclusion/state is in `{failure, error, cancelled,
timed_out}`. External `StatusContext` entries count. Only when that merged list is
empty may you declare "no failures" or fast-path "not our failure."

For external `StatusContext` entries, `targetUrl` points at the external CI — follow it
into the Jenkins/External Auth Gate below. Never classify from the status name or its
`description` string.

## GitHub Actions Retrieval

For each failing `CheckRun` from the enumeration above, resolve its run-id. The
rollup gives you the check's `detailsUrl`
(`…/actions/runs/<run-id>/job/<job-id>`) — the `<run-id>` segment is what
`gh run view` needs. If you only have a branch or SHA, `gh run list` maps it to
run-ids — used here as an Actions-scoped resolver *after* enumeration, never as the
first-line failure list:

```bash
gh run list --branch <headRefName> --status failure --json databaseId,name,conclusion
```

Then pull the failing logs:

```bash
gh run view <run-id> --log-failed
```

If `gh run view --log-failed` returns empty output, fall back to per-job logs:

```bash
gh api repos/{owner}/{repo}/actions/runs/{run-id}/jobs \
  --jq '.jobs[] | select(.conclusion == "failure") | {id, name}'
gh api repos/{owner}/{repo}/actions/jobs/{job-id}/logs
```

## Local Artifacts

If `gh` commands fail or CI is external:
- Use the provided local log file or artifact bundle when available.
- If no log source is available, ask for one. Do not classify without actual log output.

### Jenkins / External Auth Gate

For Jenkins or any authenticated external CI, resolve evidence before reasoning.
With `JENKINS_USER` plus `JENKINS_TOKEN` (or equivalent configured credentials),
fetch the console tail of the exact failing build first. The endpoint is the
build's classic URL plus `/consoleText`: drop a trailing `/`, `/console`,
`/consoleFull`, or `/consoleText` from the input, and keep any `/view/<name>/`
segment. For a matrix or multibranch failure, fetch the failing child build; the
parent build only tells you which axis or branch failed. A Blue Ocean or
dashboard URL that does not map to a job or build needs the classic build URL or
a log artifact from the user.

```bash
curl -fsSL -u "$JENKINS_USER:$JENKINS_TOKEN" "<build-url>/consoleText" | tail -200
```

Use `lastBuild` only when the input is a Jenkins job URL with no specific build number:

```bash
curl -fsSL -u "$JENKINS_USER:$JENKINS_TOKEN" "<job-url>/lastBuild/consoleText" | tail -200
```

If credentials are missing, incomplete, or the request returns auth/permission
HTML, stop and ask the user for a log excerpt, local log file, or artifact
bundle. Do not keep trying anonymous fetches. Once a log excerpt or artifact is
available, continue with classification.

The first CI LLM step must consume actual failing output, not the run page, dashboard status, or an inferred failure name.

If the input is a zip bundle:
- unzip it automatically
- locate failing logs
- split multi-job bundles into per-failure units before classification

## Large CI Manifest

For 3+ failed jobs, artifact bundles, or logs large enough that raw output would dominate the session, create local `CI_FIX.md` using [../templates/ci-fix-manifest.md](../templates/ci-fix-manifest.md).

`CI_FIX.md` owns:
- run URL / artifact paths
- failed jobs and log file paths
- failure fingerprints
- grouped root causes
- fix status
- verification status

`PROJECT.md` should only point to the active CI fix run, current phase, and `CI_FIX.md` path. Do not paste full logs into chat or PROJECT.md unless a short excerpt is decisive evidence.

Keep `CI_FIX.md` local-only. Prefer `.git/info/exclude` for workspace-specific ignores; this toolkit also ignores and hook-protects `CI_FIX.md`.

## Output

Return:

```markdown
## CI Logs Resolved

Source: <run URL | PR | local path | artifact path>
Failures found: <N>
Manifest: CI_FIX.md | none

| Failure | Job | Step | Log path/source | Notes |
|---------|-----|------|-----------------|-------|
| 1 |  |  |  |  |
```
