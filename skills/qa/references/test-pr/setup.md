# Test PR Setup

## Resolve PR Context

Detect the input format with `rules/input-detection.md`, then fetch PR metadata and diff:

```bash
gh pr view <ref> --json number,title,body,author,baseRefName,headRefName,files,additions,deletions
gh pr diff <ref>
```

Extract PR number, title, description, author notes, changed files, and any "how to test" instructions.

## Checkout Branch

Only when `--checkout` was passed:

```bash
gh pr checkout <pr-number>
```

After checkout, pause and tell the user to restart the dev server if needed. Continue only after confirmation.

## Detect App URL

Use `--url` directly when provided.

Otherwise probe common dev ports:

```bash
for port in 3000 4000 5000 8000 8080 8088 9000 9001; do
  code=$(curl -sf -o /dev/null -w "%{http_code}" --connect-timeout 1 http://localhost:$port/ 2>/dev/null)
  [ "$code" != "000" ] && [ -n "$code" ] && echo "localhost:$port -> HTTP $code"
done
```

Also inspect Docker mappings:

```bash
docker ps --format "{{.Names}}\t{{.Ports}}" 2>/dev/null | grep -E "0\.0\.0\.0:[0-9]+->"
```

Decision:

- One result: use it and state the URL.
- Multiple results: ask which is the app under test.
- No results: ask the user to start the app or provide `--url`; do not continue.

## Auth

Credentials and host classes follow `rules/preset-environments.md`. On a
production host, stop: no browser automation against production.
