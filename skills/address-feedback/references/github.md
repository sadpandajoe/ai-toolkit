# GitHub Feedback Commands

## Fetch every source

`gh pr view --comments` is for display only; it misses inline comments and
thread state.

```bash
gh pr view <number> --json reviews,comments,reviewRequests,headRefName,url
gh api --paginate repos/<owner>/<repo>/pulls/<number>/comments   # inline
gh api --paginate repos/<owner>/<repo>/pulls/<number>/reviews    # review bodies
gh api --paginate repos/<owner>/<repo>/issues/<number>/comments  # top-level
```

Thread state, needed whenever the run may reply or resolve. Page with
`-F cursor=<endCursor>` until `hasNextPage` is false:

```bash
gh api graphql -F owner=<owner> -F repo=<repo> -F number=<number> -f query='
  query($owner:String!, $repo:String!, $number:Int!, $cursor:String) {
    repository(owner:$owner, name:$repo) { pullRequest(number:$number) {
      reviewThreads(first:100, after:$cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved
          comments(first:50) { nodes { databaseId author { login } path line createdAt } } }
      } } } }'
```

Dedupe by stable IDs (`databaseId`, REST `id`, GraphQL node id) before
counting. If a source cannot be fetched, stop with the command and its output
and ask for the data; don't guess.

## Bots

Call these out by name when present:

- GitHub/Copilot: `github-actions[bot]`, `copilot-pull-request-reviewer[bot]`,
  `Copilot`, `dependabot[bot]`
- AI review: `coderabbitai[bot]`, `greptile-apps[bot]`,
  `chatgpt-codex-connector[bot]`, `ultrareview`
- Security, quality, coverage: `snyk-bot`, `codecov[bot]`, `sonarcloud[bot]`,
  `deepsource-autofix[bot]`

Any login ending in `[bot]`, containing `bot`, or matching an app pattern is a
bot unless repository convention shows it is human. Name unknown bots rather
than counting them as human reviewers.

## Reply and resolve

```bash
# Inline reply to a line-anchored review comment
gh api repos/<owner>/<repo>/pulls/<number>/comments/<comment-id>/replies -f body="<reply>"

# Resolve a thread (bot threads only)
gh api graphql -f query='mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread { isResolved } } }' -F id=<thread-node-id>
```

Reply to a top-level review summary only when it asks a direct code question,
and then as a normal PR comment that quotes enough context.

## Already done?

A rerun must not repeat a post. Before replying, look in the thread for a
comment by the authenticated user (`gh api user --jq .login`) created after
the comment you're answering; if one is there, skip it. Before resolving,
re-read `isResolved`. Before pushing, compare the local head with the remote
branch.
