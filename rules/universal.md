# AI Toolkit Rules

Always on, on Claude Code and Codex. Skills carry the facts; these are the
boundaries.

- **Read-only stays read-only.** A question, a described problem or thinking
  out loud gets your assessment, not edits, until the user asks for a change.
- **Authorization.** Committing on a feature branch, pushing it, and opening a
  draft PR for it are routine. Ask first, and wait for the user's words,
  before marking a PR ready, merging, amending or rebasing pushed commits,
  force-pushing, touching production, or any destructive action outside the
  change itself: deleting data or branches, discarding uncommitted work,
  stopping containers. Invoking `cherry-pick` authorizes its pushes to the
  target branch; invoking `watch-pr` authorizes pushing fixes to the watched
  PR's branch.
- **Stage explicit paths.** Never `git add -A` or `git add .`; unrelated work
  and local notes ride along.
- **Hooks are boundaries.** The git guard blocks `--no-verify`, force-pushing
  or deleting `main`/`master`, committing local notes (the files `handoff`
  lists) or `.ai-toolkit/`, and, unless the user started the session with
  `AITK_PR_READY=1`, a non-draft PR and `gh pr ready`/`gh pr merge`. It blocks
  `gh pr create` until `<toolkit-root>/scripts/verify.py` has recorded a
  passing check on that exact tree. A command that sets an override is
  blocked. Never work around the guard: run the real check it asks for, or
  stop and tell the user. When the pre-push check fails, fix it and push
  again.
- **Fix the behavior, not the test.** Loosen or delete a failing test only
  when the test itself is wrong, and say why in the PR.
- **Evidence for UI changes.** A user-visible change carries before and after
  screenshots or a short video from the running app, attached to the PR.
- **No PII on public surfaces, private repositories included.** PR text and
  attachment names, review replies, comments and commit messages carry no
  customer or workspace names, ticket IDs (`sc-12345`), internal URLs,
  reporter identity or credentials. Describe the configuration instead; local
  notes may keep the IDs.
- **Precedence.** These rules first, then the repository's own `AGENTS.md` or
  `CLAUDE.md`, then the toolkit's skills.
