# Gather + Triage PR Feedback

Inputs: PR number or URL; flags `--draft`, `--step` (`--auto` is a legacy
no-op alias for the default).

## Reviewer Inventory

Build the inventory before any triage. Fetch every source:

```bash
gh pr view <number> --json reviews,comments,reviewRequests
gh api --paginate repos/<owner>/<repo>/pulls/<number>/comments   # inline
gh api --paginate repos/<owner>/<repo>/pulls/<number>/reviews    # review bodies
gh api --paginate repos/<owner>/<repo>/issues/<number>/comments  # top-level
```

Unless `--draft` was passed, the run may reply to or resolve threads, so
review-thread state is required too. Page with `-F cursor=<endCursor>` until
`hasNextPage` is false:

```bash
gh api graphql -F owner=<owner> -F repo=<repo> -F number=<number> -f query='
  query($owner:String!, $repo:String!, $number:Int!, $cursor:String) {
    repository(owner:$owner, name:$repo) { pullRequest(number:$number) {
      reviewThreads(first:100, after:$cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved
          comments(first:1) { nodes { databaseId author { login } path line } } }
      } } } }'
```

Dedupe by stable IDs (`databaseId`, REST `id`, GraphQL node id) before
counting authors; `gh pr view --comments` is for display only. The inventory
table answers: which humans commented or requested changes; which bots
commented; how many top-level, review-body and inline comments each author
has; unresolved thread counts; and whether an expected source is absent.

Call out these logins when present:
- GitHub/Copilot: `github-actions[bot]`, `copilot-pull-request-reviewer[bot]`, `Copilot`, `dependabot[bot]`
- AI review: `coderabbitai[bot]`, `greptile-apps[bot]`, `chatgpt-codex-connector[bot]`, `ultrareview`
- Security/quality/coverage: `snyk-bot`, `codecov[bot]`, `sonarcloud[bot]`, `deepsource-autofix[bot]`

Treat any login ending in `[bot]`, containing `bot`, or matching an app
pattern as a bot unless repository convention proves it human; name unknown
bots instead of counting them as human reviewers.

If `gh` cannot fetch a source, or thread state is needed and unavailable,
stop with the missing command and its output and ask for the data instead of
guessing.

## Complexity

Emit the Complexity Gate block from `rules/complexity-gate.md` for the
accepted fixes. TRIVIAL with `HIGH` classification confidence uses the
quick-fix path: fix, draft the reply, summarize, and skip the full triage
table. STANDARD runs the triage table and fixes inline or in one bounded wave.
COMPLEX handling (a plan for the fix wave and the full gate ladder) applies
only when comments span subsystems, need a user or product decision, or need
more than one fix/review wave.

## Investigate

For each actionable comment, read the referenced code and its file and verify
the claim; do not assume the reviewer is correct. Check whether another guard,
caller contract or test already covers the concern. Use git blame/log when
the existing shape looks intentional.

## Triage Output

```markdown
| # | Reviewer | Comment | Verdict | Reasoning | Evidence |
|---|----------|---------|---------|-----------|----------|
| 1 | @user | ... | Fix | Actual risk | `path/file.py:42` |
| 2 | @user | ... | Skip | Why current code is valid | `path/guard.py:10` |
| 3 | @user | ... | Discuss | Trade-off or missing product decision | `path/api.py:88` |
```

- `Fix`: bugs, security issues, missing error handling, established project standards.
- `Skip`: style preference, out of scope, misunderstanding, or false positive.
- `Discuss`: architecture disagreement, ambiguous requirement, or user/product trade-off.

## Persist Triage to PROJECT.md (Hard Gate)

Append `## Feedback Triage` with the PR identity (number, URL, head branch),
the inventory table, the triage table (comment id, reviewer, verdict,
reasoning, evidence) and the open thread IDs that need resolution. It must
land before any checkpoint or fresh-worker handoff: the triage table is the
most expensive thing to reconstruct, since it needs every comment re-fetched
and the reviewer judgment redone.

## Confirmation

Default: emit the triage table, write PROJECT.md, and go straight to fixes;
the table still appears in the final summary. `--step` pauses here for the
user to confirm or adjust verdicts before any fix or post. `--draft` runs
triage and drafts but does not post. The PROJECT.md write happens on every
path.
