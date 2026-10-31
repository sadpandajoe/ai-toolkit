---
name: review
description: Independent review of code changes. Covers a local diff or branch before a PR, someone else's GitHub PR (one or a batch), a second opinion from the other model family, and posting the review. Use when asked to review, red-team, deep-review or second-opinion a change or a plan, or to review or approve a PR. Do NOT use for replying to review comments on your own PR (use address-feedback) or root-cause investigation.
---

# Review

Never review your own change inline: the author's context hides the author's
mistakes. Review runs in a fresh context that sees only the change.

## Who reviews

- **The `reviewer` agent** reviews every change except a typo, a one-file fix
  of ten changed lines or fewer, or a zero-logic formatting, import-order or
  whitespace change, off any risky path. Give it the base ref, the
  diff, the full changed files, the preflight result (build, lint, typecheck,
  targeted tests) and any acceptance criteria. Leave out your transcript, your
  notes and any "look for X" steering.
- **A second opinion from the other model family** joins it on risky changes:
  `<skill-dir>/scripts/second-opinion.py [--base REF] [--brief TEXT] [PATH ...]`
  runs Codex from Claude Code and Claude otherwise, read-only, with the
  reviewer's instructions; `--file PLAN.md` reviews a plan instead of a
  diff. Risky, here and in the other skills, means any of:
  - login, auth, payment or data-loss paths, and any change of 40 or more
    lines to a core flow (the list in the `test-pr` skill);
  - schema or migrations, public contracts, concurrency or caching,
    cross-service behavior, backwards compatibility;
  - security-sensitive code: authentication or authorization, cryptography,
    unsanitized input, dynamic SQL or ORM input, secrets or tokens,
    permission checks;
  - in ai-toolkit itself, anything that sets a worker's model, tools, sandbox
    or permissions, or turns a fail-closed check advisory: `agents/`,
    `hooks/` (with `hooks/lib/`), `.claude-plugin/`, `.codex-plugin/`,
    `.mcp.json`, `skills/review/scripts/`;
  - the user asked for a deep or second-opinion review.
- **`--deep`** switches to the larger model at xhigh effort. Use it when the
  user says "deep review", "deep quality review" or "thermonuclear", or asks
  for an adversarial, security or architecture pass, and put the angle in
  `--brief`.
- **Code judo**, on an explicit ask or a `refactor:` title, is second-opinion
  `--deep` with this brief: propose behavior-preserving restructurings that
  delete complexity; for each, name what disappears (file:line), the smaller
  model that replaces it, and why behavior is unchanged with its weakest
  point; no severity tags; "no simplification found" is a valid answer.
  Proposals go in their own section, never among the findings.

When second-opinion cannot run (CLI missing, not logged in), say so. Never
describe a same-family review as cross-family.

## Weighing findings

The reviewer is told to favor coverage, so check each `[major]` and `[minor]`
against the code before acting, and reject with one line of evidence. A
`[major]` that only one reviewer raised stays a `[minor]` until the other
reviewer also raised it, its failure reproduces, its locking assertion fails,
or the other family confirms it when asked about that finding alone.

Reviewing local changes means review and fix by default; "don't change
anything" means report only. Substantive fixes get one delta review; a finding
class that survives it goes to the user, not to a third round.

## Someone else's PR

```bash
gh pr view <ref> --json title,body,author,baseRefName,headRefName,files
gh pr diff <ref>
gh api repos/{owner}/{repo}/pulls/{number}/files --paginate   # diff positions for inline comments
```

For login, auth, payment, data-loss or contract changes, check the premise
first: read the linked issue and earlier comments. A wrong premise is the
primary finding.

Recommend **Approve** when there is no accepted `[major]`, **Request changes**
for any accepted `[major]`, and **Comment** when only `[minor]` findings need
attention.

Asking for a review does not authorize posting it. Show the findings with
severity and evidence, then post only what the user confirms; `--auto` skips
that confirmation and `--draft` never posts. Before posting, check the PR's
reviews for one already posted by the current `gh` user on the same head
commit, so a rerun does not post twice. Posting voice:
[references/posting.md](references/posting.md).

**Several PRs or `--all-open`:** you fetch each PR's diff and hand it to one
`reviewer` agent per PR (agents neither fetch nor post), at most three at a
time. You post. End with one table: PR, recommendation, key finding, posted.
