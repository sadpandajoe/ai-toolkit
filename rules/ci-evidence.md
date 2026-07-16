# CI Evidence

## Golden Rule

**A CI signal is a summary. Evidence is the artifact behind it.** Before you classify
any CI state — failing *or* passing — open the artifact. Never classify from a check
name, a status string, or a list view.

This is not a restatement of "evidence over assumptions." It names a specific trap:
the summary layer is *confidently wrong*, so nothing prompts you to look further.

## The Three Liars

| Summary signal | What it hides | Open instead |
|---|---|---|
| `gh run list` / `gh pr checks` | External CI (Jenkins, Buildkite, CircleCI) is not a GitHub Action and does not appear. A single noisy Actions failure makes the view look "explained." | `gh pr view <n> --json statusCheckRollup` — includes `CheckRun` **and** `StatusContext` |
| A check's `description` string | Many pipelines POST one generic string for every failure mode. "Cannot be built" can mean a broken test. | The console log. Find the assertion/traceback, or confirm the test stage never started. |
| A **green** check | A check proves only what it asserts. A green `migration-conflict` check means "no filename collision" — not "the DAG has one head." | The thing the check *didn't* assert. |

## How to Apply

1. **Enumerate before you classify.** Fetch the merged check picture first. Count every
   entry whose state is in `{failure, error, cancelled, timed_out}`. External
   `StatusContext` entries are first-class failures.
2. **Only an empty merged list** licenses "no failures" or "not our failure."
3. **A green check is scoped, not absolute.** Before trusting one, ask what it actually
   asserts. If the thing you care about isn't in that scope, verify it yourself.
4. **If the artifact is unreachable** (auth wall, dead `targetUrl`), stop and ask for a
   log excerpt. Do not reason from the status name — that is the trap, not a fallback.

## Why

Three separate failures, one root cause. `gh run list` hid Jenkins → "not our failure"
on a fully-red PR. A generic status string implied infra → a real test failure went
unread. A green migration-conflict check implied a single Alembic head → 4038 tests
failed on a PR that looked clean. Each time the summary was green enough to stop the
investigation one step short of the truth.
