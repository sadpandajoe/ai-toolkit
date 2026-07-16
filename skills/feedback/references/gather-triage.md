---
tier: Standard
---

# Gather + Triage PR Feedback

## Inputs

- PR number or URL
- Flags: `--draft`, `--step` (`--auto` is a legacy no-op alias for the default)

## Gather

Detect the PR input, then run the deterministic reviewer inventory before any LLM triage.

### Reviewer Inventory (Mandatory Bash-First)

Fetch every visible review source, then print a compact reviewer/bot table:

```bash
gh pr view <number> --json reviews,comments,reviewRequests \
  --jq '
    [
      (.reviews[]? | [(.author.login // "unknown"), (.state // "UNKNOWN"), "review"]),
      (.comments[]? | [(.author.login // "unknown"), "COMMENT", "top-level-comment"]),
      (.reviewRequests[]? | [(.login // .slug // .name // "unknown"), "REQUESTED", (.__typename // "review-request")])
    ][]
    | @tsv
  ' | sort

gh api --paginate repos/<owner>/<repo>/pulls/<number>/comments \
  --jq '.[] | [.user.login, "COMMENT", "inline-review-comment", (.path // ""), (.line // .original_line // "")] | @tsv' \
  | sort

gh api --paginate repos/<owner>/<repo>/pulls/<number>/reviews \
  --jq '.[] | [(.user.login // "unknown"), (.state // "UNKNOWN"), "review-submission", (.body // "" | length)] | @tsv' \
  | sort

gh api --paginate repos/<owner>/<repo>/issues/<number>/comments \
  --jq '.[] | [.user.login, "COMMENT", "top-level-issue-comment"] | @tsv' \
  | sort
```

If the workflow may reply to or resolve threads (the default; `--draft` is the exception), GraphQL review-thread data is mandatory before triage. Include unresolved counts in the inventory and stop if thread state cannot be fetched.

When combining the sources above, dedupe by stable IDs (`databaseId` / REST `id` / GraphQL node id) before counting authors. `gh pr view --comments` is useful for display, but paginated REST/GraphQL IDs are the inventory authority.

Use this paginated query shape for unresolved thread inventory. For the first page, omit `cursor`; for later pages add `-F cursor=<endCursor>` from the prior `PAGEINFO` row. Repeat until `hasNextPage` is false:

```bash
gh api graphql -F owner=<owner> -F repo=<repo> -F number=<number> -f query='
  query($owner:String!, $repo:String!, $number:Int!, $cursor:String) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$number) {
        reviewThreads(first:100, after:$cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            isResolved
            comments(first:1) {
              nodes {
                databaseId
                author { login }
                path
                line
              }
            }
          }
        }
      }
    }
  }' \
  --jq '.data.repository.pullRequest.reviewThreads as $threads
    | ($threads.nodes[] | [(.id // ""), (.comments.nodes[0].databaseId // ""), (.comments.nodes[0].author.login // "unknown"), (if .isResolved then "resolved" else "unresolved" end), (.comments.nodes[0].path // ""), (.comments.nodes[0].line // "")] | @tsv),
      (["PAGEINFO", ($threads.pageInfo.hasNextPage|tostring), ($threads.pageInfo.endCursor // "")] | @tsv)' \
  | sort
```

The inventory must explicitly answer:
- Which human reviewers commented or requested changes
- Which bots commented, including known review/security/coverage bots when present
- How many top-level, review-body, and inline comments each author has
- Whether any known expected source is absent or inaccessible

Known bot/reviewer logins to call out explicitly when present:
- GitHub/Copilot: `github-actions[bot]`, `copilot-pull-request-reviewer[bot]`, `Copilot`, `dependabot[bot]`
- AI review: `coderabbitai[bot]`, `greptile-apps[bot]`, `chatgpt-codex-connector[bot]`, `ultrareview`
- Security/quality/coverage: `snyk-bot`, `codecov[bot]`, `sonarcloud[bot]`, `deepsource-autofix[bot]`

Also treat any login ending in `[bot]`, containing `bot`, or using a known app/service pattern as a bot bucket unless repository convention proves it is a human account. Do not let unknown bots fall into the generic human reviewer count without naming them.

Do not begin triage until the inventory is complete. If `gh` cannot fetch one source, stop with the missing command/output and ask for the data instead of guessing.

After the inventory, fetch the detailed top-level discussion and inline review comments for investigation:

```bash
gh pr view <number> --comments
gh api --paginate repos/<owner>/<repo>/issues/<number>/comments
gh api --paginate repos/<owner>/<repo>/pulls/<number>/comments
gh api --paginate repos/<owner>/<repo>/pulls/<number>/reviews
```

## Complexity Gate

Classify scope before acting:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Comment count | 1-2 | 3-6, one subsystem | 7+ or several subsystems |
| Fix type | Cosmetic, naming | Contained logic or test update | Behavioral, architectural, or cross-cutting |
| Scope | Single file/area | Single subsystem | Cross-cutting |
| Discussion items | 0 | 0-1 with clear answer | 1+ requiring user/product decision |

Emit the Complexity Gate block from `rules/complexity-gate.md`.

Trivial plus confidence 8/10 or higher can use the quick-fix path: fix, draft the reply, summarize, and skip the full triage table. Posting is the default boundary; hold posts only under `--draft` or `--step`.

Moderate path: run the triage table, fix approved items inline or in one bounded wave, verify, then draft replies. Use full standard handling only when comments span subsystems, require user/product decisions, or need multiple fix/review waves.

## Investigate

For each actionable review comment:

- Read the referenced code and surrounding file.
- Verify the claim; do not assume the reviewer is correct.
- Check whether another guard, middleware, caller contract, or test already covers the concern.
- Use git blame/log when the existing shape looks intentional.

## Triage Output

Always produce this table. With `--step`, present it and wait for approval before fixing; otherwise emit it and proceed:

```markdown
| # | Reviewer | Comment | Verdict | Reasoning | Confidence |
|---|----------|---------|---------|-----------|------------|
| 1 | @user | ... | Fix | Evidence and actual risk | 9/10 |
| 2 | @user | ... | Skip | Evidence for why current code is valid | 7/10 |
| 3 | @user | ... | Discuss | Trade-off or missing product decision | 5/10 |
```

Verdicts:

- `Fix`: bugs, security issues, missing error handling, established project standards.
- `Skip`: style preference, out of scope, misunderstanding, or false positive.
- `Discuss`: architecture disagreement, ambiguous requirement, or user/product trade-off.

## Persist Triage to PROJECT.md (Hard Gate)

Before the Confirmation Gate, append a `## Feedback Triage` section to PROJECT.md containing:

- PR identity (number, URL, head branch)
- The Reviewer Inventory table from earlier in this reference
- The triage table (comment id, reviewer, verdict, reasoning, confidence)
- Open thread IDs that need resolution

This is the source of truth for resuming after `context_reset`. The triage table is the most expensive thing to reconstruct (it requires re-fetching every comment + redoing reviewer judgment), so it MUST land in PROJECT.md before any checkpoint + context_reset. STANDARD path: do not invoke checkpoint + context_reset after triage until this section exists in PROJECT.md.

## Confirmation Gate

Default: no pause — emit the triage table, complete the PROJECT.md write, and proceed straight to fixes. The triage table must still appear in the final summary.

With `--step`: pause after triage and the PROJECT.md write. Ask the user to confirm, adjust verdicts, or override; do not start fixing or posting until approved.

`--draft` still runs triage and draft response work, but does not post.
The PROJECT.md write is required on every path.
