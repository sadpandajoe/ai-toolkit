# Generate Pull Request

> **When**: You have committed changes on a feature branch and want a well-written PR with a human-readable title and description.
> **Produces**: A GitHub PR with title and body derived from commits, diff, and PROJECT.md context.

## Effect Boundary

Effect: `external_effect`.

## Usage

```
create-pr                    # Create PR from current branch
create-pr --base develop     # Target a specific base branch
create-pr --draft            # Create as draft PR (what the covered workflows chain into)
create-pr --watch            # After creation, chain into watch-pr on the new PR
```

## Steps

This workflow owns PR creation only. It does not review or rewrite code. Keep
context bounded: gather enough diff and PROJECT.md context to write the PR,
summarize large diffs by area, and do not paste full diffs unless blocked.

Creating a PR may require pushing the current branch to a remote. Treat a standalone `create-pr` as authorization to push the current feature branch only when needed for PR creation (step 1); never push unrelated branches or amend/rebase history.

**Chained** means invoked by a workflow (`create-feature`, `fix-bug`, `fix-ci`,
`create-tests`, `update-tests`) after it pushed; **standalone** means the user
invoked it. A chained run never pushes and never asks.

## Authorization Boundary

Authorization mode: `invocation`. Invocation authorizes the bounded current
feature-branch push and one PR creation described here; rewritten PII, unrelated
branches, or history rewriting remain outside that grant. A covered workflow's
automatic step is the invocation for `--draft` only: marking a PR ready for
review, requesting reviewers, and merging need the user's own words, and a
non-draft PR needs them too.

### 1. Validate Branch State

- Ensure the review gate is recorded: `bin/aitk project-state show` must list
  `review` as `PASS` for the current phase (`hooks/require-review-gate.sh`
  blocks `gh pr create` otherwise). When it does not, including when there is
  no snapshot because the change fit no other workflow, run `review-code` on
  the branch first, then continue. Invoking `create-pr` already authorizes this;
  do not ask the user to choose between an override and a review. `SKIP_PR_GATE`
  is the user's override alone.

- Once Base identity (below) resolves `$base`, verify the current branch is not
  `main` (or the repo's default branch), and count commits ahead of it:
  `git log "$base"..HEAD --oneline`.

- **Head identity.** Resolve the remote, ref, and sha the PR will be created
  from, never a guess. Run once:

```bash
branch=$(git symbolic-ref --quiet --short HEAD) || { echo "STOP: detached HEAD"; exit 1; }
IFS='|' read -r up_remote up_ref push_remote push_ref < <(git for-each-ref \
  --format='%(upstream:remotename)|%(upstream:remoteref)|%(push:remotename)|%(push:remoteref)' "refs/heads/$branch")
[ -n "$up_remote" ] && [ "$up_ref" = "refs/heads/$branch" ] \
  || { echo "STOP: no upstream or renamed upstream ref (${up_remote:-none} ${up_ref:-none})"; exit 1; }
[ -z "$push_remote" ] || [ "$push_remote" = "$up_remote" ] \
  || { echo "STOP: push remote $push_remote differs from upstream remote $up_remote"; exit 1; }
[ -z "$push_ref" ] || [ "$push_ref" = "refs/heads/$branch" ] \
  || { echo "STOP: renamed push ref $push_ref"; exit 1; }
remote=$up_remote
remote_sha=$(git rev-parse --verify --quiet "$branch@{upstream}") || { echo "STOP: no remote-tracking ref for $branch"; exit 1; }
[ "$remote_sha" = "$(git rev-parse HEAD)" ] || { echo "STOP: $remote/$branch is at $remote_sha, HEAD differs"; exit 1; }
printf 'remote=%s\nref=refs/heads/%s\nsha=%s\n' "$remote" "$branch" "$remote_sha"
```

  On a `STOP:` line, go no further without the handling below. **Standalone**:
  before any push, refuse `main`, `master`, or the branch that
  `git symbolic-ref --quiet --short "refs/remotes/<remote>/HEAD"` names (when
  set) and pause; the full default-branch check still follows Base identity.
  When the branch has no upstream (`up_remote` is empty), pick `<remote>` from
  `branch.<name>.pushRemote`, else `remote.pushDefault`, else `origin`; when
  more than one target is plausible, pause (ambiguous push target). Run
  `git push -u "<remote>" HEAD`, then the block once more. When the branch
  already has an upstream and the remote sha differs from `HEAD`, require
  `git rev-parse --abbrev-ref "<branch>@{upstream}"` to equal
  `<remote>/<branch>` (the upstream's own remote), else pause (ambiguous push
  target). Then push explicitly with
  `git push "<remote>" "HEAD:refs/heads/<branch>"` (never a bare `git push`,
  never `-u`), then the block once more; a refusal pauses (ambiguous push
  target). Any other
  `STOP` (detached head, renamed upstream ref, renamed push ref, push remote
  differing from the upstream remote) pauses. **Chained**: any `STOP` creates nothing,
  reserves nothing, and returns `## PR Not Opened` with the line `pushed —
  awaiting PR request (<reason>)`; that is a hold, not `blocked`.

- **Head repo.** Normalize the push URL of `$remote` to lowercase `owner/repo`
  (`git@github.com:O/R.git`, `https://github.com/O/R[.git]`,
  `ssh://git@github.com/O/R.git`); any other form leaves `head_repo` empty,
  which is a `STOP` as above.

```bash
head_repo=$(git remote get-url --push "$remote" | sed -E -n 's#^(git@github\.com:|https://github\.com/|ssh://git@github\.com/)([^/]+/[^/]+)$#\2#p' | sed -E 's#\.git$##' | tr '[:upper:]' '[:lower:]')
```

- **Base identity.** Resolve the base repository and default branch:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,isFork
```

  `base_repo` is `nameWithOwner` lowercased; `base` is `--base`, else the
  default branch name; on the same-repo path `head_owner=${base_repo%%/*}`.
  Chained preconditions: `head_repo` equals `base_repo` and `isFork` is
  `false`; otherwise `## PR Not Opened` with the reason. Standalone with a fork
  head: `head_owner=${head_repo%%/*}`.

- **Existing PR lookup.** Run only when `branch`, `head_repo`, `base_repo`, and
  `head_owner` are all non-empty (an empty one is a `STOP`), over every page of
  open PRs:

```bash
BRANCH="$branch" HEAD_REPO="$head_repo" gh api --paginate -X GET "repos/$base_repo/pulls" \
  -f state=open -f per_page=100 -f head="$head_owner:$branch" \
  --jq '.[] | select(.head.ref == env.BRANCH and ((.head.repo.full_name // "") | ascii_downcase) == env.HEAD_REPO) | [.number, .draft, .base.ref, .html_url] | @tsv'
```

  Row rules (here, and for reconciliation after a failed step 7):

  - A non-zero exit, an unparseable row, fewer than four fields, or an empty
    field is **indeterminate**: nothing is created or reserved. Chained returns
    `## PR Not Opened` with the reason; standalone ends with `pr_created: no`
    and status `blocked`.
  - Keep rows whose base is `$base`. Exactly one: reuse it, emit `## PR Exists`
    (`Existing: yes`, Draft from the row), reserve nothing. Two or more: stop
    with a PR conflict (chained: `## PR Not Opened`).
  - No row on `$base` but other rows: chained, or standalone without `--base`,
    stop with `PR conflict: open PR #<n> for <head> targets <existing-base>;
    this run resolved <base>; nothing created` (chained: `## PR Not Opened`). Standalone with an explicit
    `--base` proceeds.
  - No rows: continue with steps 2-6 (including the PII scrub and any pause);
    then, chained from a `published_pr` owner, emit `## PR Ready` (step 6b)
    before step 7; otherwise (standalone, or chained from `create-tests` or
    `update-tests`) go to step 7.
  - Reconciliation after a failed or unknown step 7: exactly one row reuses the
    PR, and the owner applies the reservation with `--operation-id phase:<name>`
    and `--result-digest sha256:<sha256 of html_url>`. No rows: retry step 7
    once with the same operation ID; still failing is status `blocked`, the
    pending effect stays, and the report names the retry command.
  - Never run `gh pr ready` or `gh pr edit` on an existing PR; reuse a draft or
    ready PR as it is.

### 2. Gather Context

Collect all available context for generating the PR:

**From git:**
- `git log base..HEAD --oneline` — commit titles
- `git log base..HEAD --format="%B"` — full commit messages
- `git diff base..HEAD --stat` — changed files summary
- `git diff base..HEAD --name-only` — changed file list
- targeted diffs only when a section needs details that commits, stats, names, PROJECT.md, and templates cannot answer

**From PROJECT.md** (if it exists):
- Feature Brief or Overview — for the "why"
- Implementation Notes — for technical details
- Key decisions — for the "what we chose and why"

**From repo PR template** (check in order):
- `.github/pull_request_template.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `docs/pull_request_template.md`

### 3. Generate PR Title

Rules:
- Under 70 characters
- Follow the repo's commit prefix convention (detect from recent merged PRs via `gh pr list --state merged --limit 5 --json title`)
- Human-readable — describe the user-facing "what", not the implementation detail
- Examples: "feat: Add bulk filter editing for dashboards", "fix: Prevent chart crash on empty datasets"

**Tightness check before finalizing.** Ask three questions; if any answer is no, rewrite:

1. **Does every term in the title appear in a commit message, code comment, or external doc?** — Conversation-internal jargon ("channel-3", "Tier A", "Layer 2", or any label invented during planning that didn't make it into the codebase) is opaque to readers. Replace with the concrete domain term it stood for.
2. **Does the title lead with the outcome, not the mechanism?** — "Add helper class X" / "Introduce normaliser Y" / "Refactor to pattern Z" describe what the code looks like; readers want to know what changes for users of the affected area. Lead with the problem solved or the capability gained.
3. **Could a reader grep their codebase from this title to assess relevance?** — If the PR introduces an API that callers will adopt, name 1-2 of the key entry points (function names, route paths, env vars) so readers don't have to open the diff to know whether it touches their code.

**Common anti-patterns to flag and rewrite:**

| Anti-pattern | Example | Rewrite as |
|---|---|---|
| Invented abstraction label | `feat: introduce channel-3 helpers` | `feat: helpers for browser-direct navigation` |
| Mechanism-first phrasing | `feat: add URL normaliser to API client` | `feat: strip backend URL prefixes for subdirectory deployments` |
| Generic verb + noun | `chore: refactor exports` | `chore: collapse duplicate path utility into navigation module` |
| Multi-thing list | `feat: helpers + normaliser + lint rule` | Pick the most user-visible outcome; mention secondaries in body |

For dual-purpose PRs (feature + fix), pick the framing that matches the most user-visible outcome — even if the conventional-commits prefix is `feat`, the title text can lead with the problem ("prevent X bug via helpers Y").

### 4. Generate PR Body

If a PR template exists, fill in each section from the gathered context.

If no template, use this default structure:

```markdown
## Summary
[1-3 bullet points: what changed and why, written for someone who doesn't know the codebase]

## Changes
[Grouped by area — not a file list, but a logical description of what each group of changes does]

## Test plan
[How to verify: automated tests, manual steps, or both]

## Related
[Link to ticket, issue, or prior PR if referenced in commits or PROJECT.md]
```

For a bug fix with a validated RCA in PROJECT.md or the commit context, replace
the generic `Changes` section with this causal structure:

```markdown
## Incident Root Cause
[The single cause of the user-visible failure]

## Latent Bugs / Hardening
[Separate correctness issues fixed in the same PR; omit when there are none]

## Fix
[What changed, grouped by the problem each change addresses]
```

Do not blend opportunistic hardening into the incident cause. This keeps the
blocking fix distinct from secondary correctness improvements.

**Body tightness check.** The same anti-patterns from the title check apply to the opening summary — readers form their first impression from the first paragraph. Specifically:

- **Don't import conversation jargon into the body.** If a label was useful for organizing the planning discussion (channels, tiers, layers, phases) but never made it into commit messages or code, do not introduce it for the first time in the PR body. The reader can't follow back to where it was defined.
- **Open with the user-visible problem or capability**, not the file list or the helper inventory. The reader decides whether to keep reading based on the first 1-2 sentences.
- **Move implementation detail tables / file inventories below the rationale**, not above. Tables of "what's in this PR" are useful to maintainers but bury the answer to "why does this PR exist".
- **Strip planning artefacts** — "skeleton commit", "first set of tests", "stubs that throw" — once the PR has grown past that phase. The body should reflect the PR's *current* state, not its development history.

### 5. PII Scrub

Before showing the PR to the user, re-read the drafted title and body and remove anything that should not appear on a public surface. The PR text is permanent — edits after the fact don't remove it from git history, mirrors, or search indexes.

Strip or paraphrase:
- **Customer or workspace names** — say "a customer" or describe the configuration ("dashboards with `hideTab: true`") instead.
- **Internal ticket IDs** — Shortcut (`sc-XXXXX`), Linear, Jira, internal issue tracker IDs. These belong in PROJECT.md, the local commit footer, or an internal channel, not in the public PR body.
- **Internal URLs** — links to Shortcut/Linear/Jira tickets, internal dashboards, staging workspaces, customer-specific Superset/Preset instances.
- **Reporter identity** — never name the customer, support engineer, or internal user who reported the bug.
- **Credentials and connection strings** — even in test plans (use placeholders).

Public repo PR bodies, PR titles, and commit messages are all in scope. If the repo is a private/internal monorepo, the rule still applies for customer-identifying data — assume the audience is broader than the current team.

If you find PII, rewrite it generically and re-run the title/body tightness checks on the result before continuing.

### 6. Present for Review

Default: print the generated title and body for visibility and proceed directly to step 7 — invoking `create-pr` is the authorization to create the PR, and the step-5 PII scrub covers the irreversible-text risk.

Pause and wait for confirmation only when:
- the step-5 scrub actually found and rewrote PII (show the rewrite, confirm before posting), or
- `--step` was passed (restores the always-pause behavior).

A "no PR" answer at this pause ends `create-pr` with `pr_created: no` before any
`## PR Ready` yield.

### 6b. Reservation Yield (chained from a `published_pr` owner)

After the step-5 rewrite and any step-6 confirmation, and before step 7, a run
chained from `create-feature`, `fix-bug`, or `fix-ci` stops and returns this
block to its owner, which reserves the `published_pr` effect and then resumes at
step 7. Standalone runs and runs chained from `create-tests` or `update-tests`
go straight to step 7: no yield, no reservation.

```markdown
## PR Ready
Title: <title>
Base ← Head: <base> ← <head_owner>:<branch>
Draft: yes
Existing: no
```

### 7. Create PR

Hook-enforced precondition, outside this workflow's contract: `hooks/require-review-gate.sh`
blocks `gh pr create` unless the `PROJECT.md` routing snapshot records the
review gate `PASS` (`bin/aitk project-state show`). Without it, run
`review-code` first. Never override the hook on your own: stop and ask the
user, who alone can override it for a change outside any workflow.

```bash
gh pr create [--draft] --base "$base" --head "$head_owner:$branch" --title "..." --body "..."
```

Return the PR URL. The identity flags pin the head the lookup used.

### Early Returns

Reuse and holds skip steps 2-9: nothing is created, no `## PR Created` entry is
written, and metrics record `pr_created: no`.

```markdown
## PR Exists
PR #<n>: <url>
Base: <base> ← <branch>
Draft: <yes | no>
Existing: yes
```

```markdown
## PR Not Opened
Reason: <identity STOP | precondition | PR conflict | indeterminate lookup>
Record: pushed — awaiting PR request (<reason>)
```

### 8. PROJECT.md Update (Hard Gate)

Before emitting the chat summary, append a `## PR Created` entry to PROJECT.md so the project state reflects the new PR. Without this write, a fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md) immediately after `create-pr` loses the PR pointer and the next session has no record that the PR exists.

```markdown
## PR Created
PR #[number]: [title]
URL: [link]
Base: [base] ← [head branch]
Commits: [N]
Draft: [yes/no]
```

If a prior phase (`create-feature`, `fix-bug`, etc.) has an open entry in PROJECT.md whose work this PR ships, mark that entry resolved in the same write rather than leaving it dangling.

Emit before the chat summary:

```markdown
## PROJECT.md Updated — PR Created
PR #[number] recorded; prior phase entry: [resolved / none / kept]
```

### 9. Summary

Do not emit this summary until the `## PROJECT.md Updated — PR Created` confirmation block has been emitted.

```markdown
## Create-PR Complete
PR #[number]: [title]
URL: [link]
Base: [base branch] ← [head branch]
Commits: [N]
```

**Record metrics** when available for the workflow:
- `command`: `create-pr`
- `complexity`: `standard`
- `status`: `clean` if the PR was created, `blocked` otherwise
- `rounds`: 0
- `gate_decisions`: `{ pr_created: <yes | no>, draft: <yes | no> }`
- `worker_usage`: subagent/worker invocation counts when applicable

### 10. Watch Handoff

With `--watch`, chain directly into `watch-pr <new-pr>` — the flag is the explicit pre-authorization for the watch's standing commit+push grant. Without it, when the PR has CI checks, end with a one-line suggestion: `Next: watch-pr #<number> to babysit CI and review comments.` Never enter the watch without the flag; entering it grants standing push authority, which must be the user's explicit choice.

## Notes
- This command generates and creates the PR — it does not review the code
- For code review before PR, use `review-code` first
- For reviewing someone else's PR, use `review-pr`
- The title and body are printed before creating; the command pauses for approval only on a PII-scrub rewrite or `--step` (see step 6)
- Covered workflows chain here with `--draft` after their own push; `--no-pr` on the workflow skips this command
