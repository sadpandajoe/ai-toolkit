# Universal Principles

These rules load in every session, on Claude and on Codex; workflows and skills
carry the detail.

- **Multi-step and publishing work enters a workflow first.** A request whose
  change takes several steps, or that will push or open a PR, loads the
  `workflows` skill before the first edit or PR action, on intent alone. Emit
  `Workflow entered: <name>` (or `none — <why>` when no workflow matches) and,
  once a workflow is entered, persist the routing snapshot before touching
  files. A contained edit with a passing check runs inline: make it, run the
  check, report the result (`Workflow entered: none — contained edit`). Small
  direct answers, read-only work, and fixed-procedure skills that change no
  repo behavior (commit, archive) are exempt; a domain skill that edits
  behavior runs inside the workflow, not instead of it.
- **Read-only work stays read-only.** When the user describes a problem, asks a
  question, or thinks out loud rather than asking for a change, the deliverable
  is your assessment: report what you found and stop. Answers, reviews, and
  diagnostics create or modify no workflow state unless the user asks for a
  report artifact.
- **Durable state is files, not chat.** `PROJECT.md` holds current state and the
  routing snapshot; `PLAN.md` holds the active plan when one was needed. Both
  are local-only, never committed, and written only by the parent session;
  workers return compact handoffs (`rules/specialist-handoff.md`). Update them
  before each worker dispatch and after each handoff, so a fresh session can
  continue from them alone and no workflow needs, or asks for, a cleared
  context or a new session. Resume from the files, never from remembered chat;
  task lists only mirror them. To edit one that is a symlink, write to its
  `readlink -f` target: Claude Code's Write and Edit refuse to write through a
  symlink.
- **No PII on public surfaces.** No customer names, ticket IDs (`sc-XXXXX`,
  Linear, Jira), customer URLs, or reporter identity in PR titles, bodies,
  comments, or commit messages. Describe behavior generically. Local files and
  chat summaries may carry the IDs.
- **Evidence before completion.** A gate passes on a check that ran and its
  result, never on inspection alone; a syntax-only check, or a command that
  failed to start, is not that check. Report results as they happened: a
  failure with its output, a skipped step as skipped. Never push after a failed
  verification.
- **Resolve uncertainty yourself.** Investigate, read code, and run checks
  rather than asking. Ask the user only for a genuine product, design, or scope
  choice, a fact only they hold, or a protected effect; those are the only
  `USER_DECISION` cases. A passing gate moves the workflow to its next step
  without asking; only `USER_DECISION`, `BLOCKED`, and hard safety gates pause
  it (`rules/gates.md`).
- **Deliver the scope that was asked.** Make routine judgment calls yourself.
  If the request looks mistaken or a better approach exists, say so in a
  sentence and continue as asked. Cleanup, refactors, and fixes the task did
  not call for go in the summary as suggestions.
- **Commit, push, and open a draft PR freely; promote only on request.** Once
  verification and review pass, commit to the current feature branch, push it,
  and open a **draft** PR through `create-pr --draft`, without asking "should I
  commit/push?". Workflow runs only; never from `main`; `--no-pr` opts out and
  leaves the work `pushed — awaiting PR request`. Marking a PR ready for
  review, requesting reviewers, merging, and opening a non-draft PR need the
  user's explicit words. Amend, rebase, force-push, and pushes to
  `main`/`master`/protected branches need explicit authorization.
  When the user asks for a PR on a change that never entered a workflow (a
  chore, a config tweak), run `review-code` on the branch first so the review
  gate is recorded, then open the PR; never hand the user an
  override-or-review choice.
- **Confirm before destructive actions.** Deleting data or branches, discarding
  uncommitted work, stopping containers, and other irreversible effects outside
  the change itself wait for the user's confirmation; the commits, pushes, and
  draft PR above are routine. Before starting Docker stacks, follow
  `skills/preflight/rules.md`; before large test runs, `skills/testing/rules.md`.
- **Review is independent.** Never review your own work inline; review and
  validation run in a fresh context, preferably on the other provider. A routed
  specialist that reports `MODEL_ROUTE_UNAVAILABLE` stays unavailable: no
  generic worker or cheaper model takes its place.

## Precedence

When two rules disagree, the earlier source wins: this file; gates and safety
contracts (`rules/gates.md`, `interfaces/contracts.json`); the repository's own
guidance (its `AGENTS.md`, `CLAUDE.md`); orchestration and model rules; domain
rules (testing, implementation, review); `PROJECT.md` current state. Repository
conventions beat toolkit style and domain rules; toolkit safety and
authorization never yield to them.
