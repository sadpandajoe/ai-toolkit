# Universal Principles

These rules load in every session, on Claude and on Codex; workflows and skills
carry the detail. "(hook-enforced)" marks an absolute that a hook blocks even
when this text is missed.

- **Multi-step and publishing work enters a workflow first.** A request whose
  change takes several steps, or that will push or open a PR, loads the
  `workflows` skill before the first edit or PR action, on intent alone, and
  persists the routing snapshot before touching files. A contained edit with a
  passing check runs inline: make it, run the check, report the result. Small
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
  are local-only, never committed (hook-enforced), and written only by the
  parent session, so one writer keeps them consistent; workers return compact
  handoffs (`rules/specialist-handoff.md`). Update them before each worker
  dispatch and after each handoff, so a fresh session or worker can continue
  from the files alone and no workflow needs, or asks for, a cleared context.
  Resume from the files, never from remembered chat, which compaction loses.
  To edit one that is a symlink, write to its
  `readlink -f` target: Claude Code's Write and Edit refuse to write through a
  symlink.
- **No PII on public surfaces.** PR text, comments, and commit messages carry
  no customer names, ticket IDs, internal URLs, or reporter identity; scrub
  them per `rules/pii-scrub.md`.
- **Evidence before completion.** A gate passes on a check that ran and its
  result, never on inspection alone; a syntax-only check, or a command that
  failed to start, is not that check. Report results as they happened: a
  failure with its output, a skipped step as skipped. Never push after a failed
  verification, because CI and reviewers would inherit a known failure.
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
- **Deliver with `bin/aitk deliver`; promote only on request.** After
  verification and review pass it commits, pushes the feature branch, and opens
  a **draft** PR without asking; `--no-pr` stops at `pushed — awaiting PR
  request`. Never from `main`. Hook-enforced: no `--no-verify`, no
  `gh pr create` before review `PASS`, and no non-draft PR, ready, or merge
  without the user's words (`AITK_PR_READY=1`). Amend, rebase, and force-push
  need explicit authorization (force-push or delete of `main` is
  hook-enforced); invoking `cherry-pick` or `watch-pr` grants their
  fast-forward pushes.
- **Confirm before destructive actions.** Deleting data or branches, discarding
  uncommitted work, stopping containers, and other irreversible effects outside
  the change itself wait for the user's confirmation, because they cannot be
  undone; the commits, pushes, and draft PR above are routine. Before starting
  Docker stacks or large test runs, follow `rules/resource-management.md`.
- **Review is independent.** Never review your own work inline, because the
  author's context hides the author's mistakes; review and validation run cold
  in a fresh context (`rules/specialist-handoff.md`), preferably on the other
  provider. A routed specialist that reports `MODEL_ROUTE_UNAVAILABLE` stays
  unavailable: no generic worker or cheaper model takes its place, since it
  would grade below the route's standard.
- **Record what overturned you.** When a user corrects you, a route was wrong,
  or a specialist overturned a plan or RCA, record it with `bin/aitk observe
  --kind <user-correction | misroute | specialist-invalidation> --detail
  "<one sentence>"`.

## Precedence

When two rules disagree, the earlier source wins:

1. safety and authorization in this file;
2. gates and contracts (`rules/gates.md`, `interfaces/contracts.json`);
3. the repository's own `AGENTS.md` and `CLAUDE.md`;
4. toolkit orchestration and domain rules (model routing, testing,
   implementation, review);
5. `PROJECT.md` current state.

Repository conventions beat toolkit style and domain rules; toolkit safety and
authorization never yield to them.
