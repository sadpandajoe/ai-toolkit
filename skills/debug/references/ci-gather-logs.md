# CI Gather Logs

Use at the start of `fix-ci` to resolve real failing log output before any
classification. Sources: a GitHub Actions run URL, a PR number, a local log
file, a local zip bundle, or (no argument) the latest failed run on the
current branch.

## Enumerate All Failures First

The merged check rollup is the **first** call, not a fallback
(`rules/ci-evidence.md`): `gh run list` and `gh pr checks` show Actions only,
and external CI posts commit statuses that never appear there.

```bash
gh pr view <number> --json statusCheckRollup,headRefName
# no PR: go via the commit, check-runs and statuses
gh api repos/{owner}/{repo}/commits/{sha}/check-runs \
  --jq '.check_runs[] | select(.conclusion == "failure")'
gh api repos/{owner}/{repo}/commits/{sha}/status \
  --jq '.statuses[] | select(.state == "failure" or .state == "error")'
```

Enumerate every entry in `{failure, error, cancelled, timed_out}`, external
`StatusContext` entries included; only an empty merged list means "no
failures". Never classify from a status name or its `description`: follow an
external entry's `targetUrl` to its log.

## GitHub Actions

Take the run id from the check's `detailsUrl`
(`…/actions/runs/<run-id>/job/<job-id>`), or resolve it after enumeration:

```bash
gh run list --branch <headRefName> --status failure --json databaseId,name,conclusion
gh run view <run-id> --log-failed
# empty output: per-job logs
gh api repos/{owner}/{repo}/actions/runs/{run-id}/jobs \
  --jq '.jobs[] | select(.conclusion == "failure") | {id, name}'
gh api repos/{owner}/{repo}/actions/jobs/{job-id}/logs
```

## Jenkins and Other External CI

With `JENKINS_USER` and `JENKINS_TOKEN` (or equivalent credentials), fetch the
console tail of the exact failing build: the classic build URL plus
`/consoleText` (drop a trailing `/`, `/console`, `/consoleFull` or
`/consoleText`; keep any `/view/<name>/` segment). For matrix or multibranch
jobs, fetch the failing child build. Use `lastBuild` only for a job URL with no
build number. A Blue Ocean or dashboard URL needs the classic build URL or a
log artifact from the user.

```bash
curl -fsSL -u "$JENKINS_USER:$JENKINS_TOKEN" "<build-url>/consoleText" | tail -200
```

Missing credentials or an auth/permission page: stop and ask for a log
excerpt, file or artifact bundle. No anonymous retries.

## Local Artifacts

Use a provided log file or zip bundle (unzip it, locate the failing logs, and
split multi-job bundles into per-failure units). With no log source, ask for
one; never classify without actual failing output.

## Large CI Manifest

For 3+ failed jobs, artifact bundles, or logs that would dominate the session,
create `CI_FIX.md` from [../templates/ci-fix-manifest.md](../templates/ci-fix-manifest.md).
It holds the sources, failed jobs and log paths, root-cause groups, and fix
and verification status; `PROJECT.md` only points to it. `CI_FIX.md` stays
local-only.

## Output

```markdown
## CI Logs Resolved

Source: <run URL | PR | local path | artifact path>
Failures found: <N>
Manifest: CI_FIX.md | none

| Failure | Job | Step | Log path/source | Notes |
|---------|-----|------|-----------------|-------|
| 1 |  |  |  |  |
```
