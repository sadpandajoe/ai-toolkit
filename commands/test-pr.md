# /test-pr - Manual PR Testing via Browser

@{{TOOLKIT_DIR}}/rules/input-detection.md
@{{TOOLKIT_DIR}}/rules/preset-environments.md

> **When**: You want to manually verify a PR's changes work correctly in a running local app.
> **Produces**: Scenario-by-scenario pass/fail results with screenshot + video evidence.

Uses Playwright MCP to drive a real browser **and records the run as a video artifact** by default (see [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md)). Project-agnostic — works for any web app on localhost or stg.

## Usage

```
/test-pr <pr-number>
/test-pr apache/superset#28456
/test-pr https://github.com/owner/repo/pull/123
/test-pr <pr-number> --url http://localhost:3000   # explicit app URL
/test-pr <pr-number> --checkout                    # check out PR branch first
/test-pr <pr-number> --smoke                       # 3 scenarios max, fast
/test-pr <pr-number> --post                        # after run, ask where to post the report
/test-pr <pr-number> --post sc-12345               # post directly to a Shortcut story
/test-pr <pr-number> --post pr                     # post directly as a comment on the PR
/test-pr <pr-number> --no-record                   # skip the video recording (rare)
```

## Prerequisite

**The app must already be running locally.** This command does not start your dev server — run that yourself first (`npm run dev`, `docker compose up`, etc.) before invoking `/test-pr`.

Use `--checkout` if you haven't switched to the PR branch yet. After checkout the command pauses so you can restart your dev server if needed.

## Steps

### 1. Resolve PR Context

Detect the input format per `rules/input-detection.md` and fetch:

```bash
gh pr view $REF --json number,title,body,author,baseRefName,headRefName,files,additions,deletions
gh pr diff $REF
```

Extract: PR number, title, description, author, changed files, and any "how to test" notes in the PR body.

### 2. Checkout Branch (only with --checkout)

```bash
gh pr checkout $PR_NUMBER
```

After switching branches, pause and tell the user:

> "Switched to PR branch `<branch>`. If your dev server needs restarting to pick up these changes, do that now — then reply to continue."

Wait for confirmation before proceeding to step 3.

### 3. Detect App URL

If `--url` was provided, use it directly and skip probing.

Otherwise probe common dev ports:

```bash
for port in 3000 4000 5000 8000 8080 8088 9000 9001; do
  code=$(curl -sf -o /dev/null -w "%{http_code}" --connect-timeout 1 http://localhost:$port/ 2>/dev/null)
  [ "$code" != "000" ] && [ -n "$code" ] && echo "localhost:$port -> HTTP $code"
done
```

Also check Docker port mappings:

```bash
docker ps --format "{{.Names}}\t{{.Ports}}" 2>/dev/null | grep -E "0\.0\.0\.0:[0-9]+->"
```

Decision:
- **One result**: use it, note in-line ("Using http://localhost:3000")
- **Multiple results**: show the list and ask which one is the app under test
- **None found**: tell the user to start the app and provide the URL — do not proceed until resolved

### 4. Assess Impact

Follow [skills/qa/references/assess-impact.md](../skills/qa/references/assess-impact.md) on the PR diff and changed files. This classifies the touched workflows as CORE, STANDARD, or PERIPHERAL and determines how many smoke scenarios to generate.

### 5. Derive Smoke Scenarios

Follow [skills/qa/references/pr-smoke-scenarios.md](../skills/qa/references/pr-smoke-scenarios.md) with:
- PR title, description, and author notes
- List of changed files and diff
- Impact assessment from step 4

This produces 3–7 focused scenarios. With `--smoke`, cap at 3 regardless of impact.

Show the scenario list to the user before executing. If they want to adjust (add, remove, or reword scenarios), accept changes before proceeding.

### 6. Execute via Playwright MCP (with recording)

Follow [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md) for the canonical recipe — start `screencapture -v -V <duration>` in the background **before** the first scenario, drive the browser via Playwright MCP, kill the recording on completion, and surface the file path. Skip the recording only if `--no-record` was passed.

For each scenario in order:

1. Navigate to the relevant page at the app URL from step 3
2. Perform the described actions using Playwright MCP (`mcp__plugin_playwright_playwright__browser_*`)
3. Take a screenshot at the primary verification point (name it `scenario-<N>-<short-name>.png`)
4. Check console for errors: `browser_console_messages`
5. Record the outcome: **PASS**, **FAIL**, or **BLOCKED**

**Auth handling**: Determine credential strategy from the app URL per `rules/preset-environments.md`:
- **Staging** (URL contains `stg.`): use `$PRESET_STG_BOT_LOGIN` / `$PRESET_STG_BOT_PASSWORD`. If either env var is unset, mark all scenarios BLOCKED and tell the user to set them before retrying.
- **Local dev**: try `admin`/`admin` then `admin`/`general`. If both fail, mark all scenarios BLOCKED and ask the user for credentials.
- **Production**: stop immediately — do not run automated tests against production.

**On FAIL**: Take an additional screenshot showing the error state. Do not retry — move to the next scenario.

**On BLOCKED**: Note what prerequisite was missing (auth, data, feature flag). Move on.

Do not run scenarios in parallel — sequential execution keeps evidence clean and the recording linear.

### 7. Report

The template below is for **in-terminal output only**. Always include the recording file path in the `Evidence` line.

If `--post` was passed (or the user asks afterward to post results to a Shortcut story, GitHub PR/issue comment, or any other shared external destination), do not adapt this terminal template. Instead:
- Read [skills/qa/references/write-report.md](../skills/qa/references/write-report.md) for canonical body shape (single-flow vs multi-scenario), tone (narrative not technical), and evidence rules. Load the matching template / example from `qa/references/write-report/` only when actually drafting.
- Read the destination-specific reference for upload + post mechanics: [skills/shortcut/references/report.md](../skills/shortcut/references/report.md) for Shortcut, or the equivalent for other destinations.
- Attach the recording from `~/qa-recordings/`. For GitHub PR comments, follow the size-limit guidance in [skills/qa/references/browser-recording.md](../skills/qa/references/browser-recording.md) (transcode to MP4 if >10 MB).

`--post` argument forms:
- `--post` (no value) → after the run, ask the user where to post (Shortcut story id, `pr`, both, or skip)
- `--post sc-12345` → post directly to that Shortcut story
- `--post pr` → post directly as a comment on the PR under test
- `--post sc-12345 --post pr` → post to both

The terminal template below specifies a tabular grid that's appropriate for in-conversation summaries only — never paste it into an external comment.

```markdown
## Test-PR Complete

PR: #<number> — <title>
Branch: <head-branch>
App: <url>
Impact: CORE / STANDARD / PERIPHERAL

### Results

| # | Scenario | Tag | Result | Notes |
|---|----------|-----|--------|-------|
| 1 | <name> | [new/fix/guard] | ✅ PASS | — |
| 2 | <name> | [fix] | ❌ FAIL | <what happened> |
| 3 | <name> | [guard] | ⚠️ BLOCKED | <what was missing> |

### Summary
- <N> passed, <N> failed, <N> blocked of <N> total

### Evidence
- Recording: ~/qa-recordings/<file>.mov (<size>)
- Screenshots: scenario-1-*.png, scenario-2-*.png, ...

### Failures
[For each FAIL — omit section if none:]
**Scenario <N> — <name>**
- Expected: <what should have happened>
- Actual: <what happened instead>
- Screenshot: scenario-<N>-fail.png
- Console errors: <if any, or "none">

### Blocked
[For each BLOCKED — omit section if none:]
**Scenario <N> — <name>**: <what was needed — auth, data, feature flag>

### Next Steps
[All pass:] PR looks good to merge.
[Failures:] Feed findings back to the PR author — specific failures listed above.
[Blocked:] Resolve blockers above and re-run `/test-pr <number>`.
```

## Notes
- **This command tests what is currently running** — make sure the right branch is checked out and the app is up before running
- For full QA validation with a curated test plan iterated to quality threshold, use `/run-test-plan` instead
- For running Superset's existing automated Playwright test suite (`.spec.ts` files), route to [skills/superset-local/references/run-playwright.md](../skills/superset-local/references/run-playwright.md) instead
- Does not modify code or file bugs — test-only output
- The `--smoke` flag is useful for a quick pre-merge sanity check; omit it for more thorough coverage on CORE-impact PRs
