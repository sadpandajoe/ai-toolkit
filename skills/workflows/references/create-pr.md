# Generate Pull Request

> **When**: You have changes on a feature branch and want a well-written PR with a human-readable title and description.
> **Produces**: A draft GitHub PR (or the open one for this head, reused), with title and body derived from commits, diff, and PROJECT.md context, and a `## PR Created` entry in PROJECT.md.

## Effect Boundary

Effect: `external_effect`.

## Usage

```
create-pr                    # Draft PR from the current branch
create-pr --base develop     # Target a specific base branch
create-pr --draft            # Same as the default: the PR is a draft
create-pr --watch            # After creation, chain into watch-pr on the new PR
create-pr --step             # Pause before the PR is created
```

## Authorization Boundary

Authorization mode: `invocation`. Invoking `create-pr` authorizes pushing the
current feature branch and opening one draft PR for it through `bin/aitk
deliver`; unrelated branches, history rewrites, and text the PII scrub
rewrote stay outside that grant. Marking a PR ready for review, requesting
reviewers, and merging need the user's own words. A non-draft PR needs them
too, and then runs `AITK_PR_READY=1 bin/aitk deliver --ready …`. Never run `gh
pr ready` or `gh pr edit` on an existing PR; reuse a draft or ready PR as it
is.

## Steps

This workflow writes the PR text; `bin/aitk deliver` pushes and opens the PR.
It does not review or rewrite code. Keep context bounded: gather enough diff
and PROJECT.md context to write the PR, summarize large diffs by area, and do
not paste full diffs unless blocked. Owning workflows (`create-feature`,
`fix-bug`, `fix-ci`, `tests`) run steps 2-5 for the
text and then their own `deliver --workflow` line.

### 1. Gates

`deliver` refuses, changing nothing, without a routing snapshot whose review
gate is `PASS` with a reviewer record and a passing `STRONG` `bin/aitk verify
--run` record for the current tree. When either is missing, including when
there is no snapshot because the change fit no other workflow, run
`review-code` on the branch first; invoking `create-pr` already authorizes
this. Do not ask the user to choose between an override and a review.

### 2. Gather Context

Ground the PR text in the commits (`git log <base>..HEAD`, subjects and
bodies), the diff stat and file list, the PROJECT.md brief, implementation
notes, and key decisions, and the repo's PR template when one exists
(`.github/pull_request_template.md` or a sibling path). Read targeted diffs
only for what those cannot answer.

### 3. Generate PR Title

Follow the repo's title convention (`gh pr list --state merged --limit 5 --json title`).
Lead with the most user-visible outcome for the affected area rather than the
mechanism, name the entry point a caller would search for when the PR adds
one, and keep it near 70 characters so PR lists show it whole.

### 4. Generate PR Body

Fill the repo's template when there is one; otherwise use Summary (what
changed and why, for a reader who does not know the codebase), Changes
(grouped by area, not a file list), Test plan, and Related. For a bug fix with
a validated RCA, use Incident Root Cause, Latent Bugs / Hardening (omit when
none), and Fix in place of Changes, so the blocking cause stays distinct from
opportunistic hardening. Open with the problem or capability, keep the body as
long as the change needs, and describe the PR as it stands, not how it was
built. Use only terms a reader can find in the code, commits, or docs: a label
coined while planning ("Tier A", "channel-3", "skeleton commit") is opaque on a
public PR, so name what it stood for.

### 5. PII Scrub

Scrub the title and body per [rules/pii-scrub.md](../../../rules/pii-scrub.md);
after a rewrite, recheck the result against steps 3-4. Write the body to a
file for step 7.

### 6. Present

Print the title and body and continue: invoking `create-pr` is the
authorization, and the scrub covers the irreversible-text risk. Pause for
confirmation only when the scrub rewrote something (show the rewrite) or with
`--step`. A "no PR" answer ends the run with `pr_created: no`.

### 7. Deliver

```bash
bin/aitk deliver --title "<title>" --body-file <file> [--base <branch>]
```

Paste the block it prints. `## PR Created` or `## PR Exists` names the PR, and
`deliver` has written the `## PR Created` entry to PROJECT.md; mark resolved
any open PROJECT.md entry whose work this PR ships. `## PR Not Opened` is a
hold (push target, head identity, fork, PR conflict, or an indeterminate
lookup): nothing was opened, so record its `Record:` line and stop with
`pr_created: no`. `## Delivery Refused` names the missing gate; nothing
changed.

### 8. Summary

Report the PR number, title, URL, base, and whether it is a draft, then record
metrics with `bin/aitk metrics emit --workflow create-pr --status <clean |
blocked> --extra 'decisions={"pr_created": "<yes|no>", "draft": "<yes|no>"}'`.

### 9. Watch Handoff

With `--watch`, chain directly into `watch-pr <new-pr>` — the flag is the explicit pre-authorization for the watch's standing commit+push grant. Without it, when the PR has CI checks, end with a one-line suggestion: `Next: watch-pr #<number> to babysit CI and review comments.` Never enter the watch without the flag; entering it grants standing push authority, which must be the user's explicit choice.
