# WATCH.md — PR Watch Manifest

Local-only, never committed (same rule as PROJECT.md / PLAN.md). One manifest per watched PR; the watch resumes from this file alone.

```markdown
# WATCH.md

## Target
- PR: #[number] — [title]
- URL: [url]
- Branch: [head] ← into [base]
- Repo: [owner/repo]

## Config
- Green target: [N] ([adaptive default / forced via --greens])
- Comment scope: bots + clear human asks
- Started: [ISO timestamp]
- Authorization: new commits + ff push to [head]; replies/resolution per scope. No amend/rebase/force-push/merge/approve.

## State
- Status: watching | stable | escalated | blocked
- Iteration: [N] / 12 (cumulative for this watch — survives context resets)
- Green streak: [N] / [target]
- Streak resets from flaky-class failures: [N] / 3
- Last checked head SHA: [sha]
- Last checked run: [run id] — [conclusion]
- Comment cursor: [ISO timestamp of newest processed comment]

## Fix Attempts
| Failure group | Pattern | Attempts | Status |
|---------------|---------|----------|--------|

## Rerun Ledger
| Run ID | Classified as | Reruns used (max 2) | Outcome |
|--------|---------------|---------------------|---------|

## Comment Ledger
| Comment ID | Author | Bot/Human | Verdict | Status |
|-----------|--------|-----------|---------|--------|

## Escalations
- [none yet]

## Iteration Log
- [timestamp] iter [N]: [one line — what was checked, what was dispatched, streak]
```

Ledger rows are append-only within a watch. Keep Iteration Log entries to one line; details live in PROJECT.md or the fix engines' own records.
