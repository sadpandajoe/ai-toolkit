# AI Toolkit Rules

These load in every session, on Claude Code and on Codex. Skills carry the
domain facts; these are the boundaries.

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
  or deleting `main`/`master`, committing local notes (`PROJECT.md`,
  `PLAN.md` and the others the `handoff` skill lists) or `.ai-toolkit/`, a
  non-draft PR, and `gh pr ready`/`gh pr merge`, unless the user started the
  session with `AITK_PR_READY=1`; a command that sets or exports an override
  is blocked. When the git guard blocks you, stop and tell the user; never work
  around it. When the pre-push check fails, fix the failures and push again.
- **Evidence for UI changes.** A change to anything a user sees carries before
  and after screenshots or a short video, captured from the running app and
  attached to the PR.
- **No PII on public surfaces.** PR text, review replies, comments and commit
  messages carry no customer or workspace names, ticket IDs (`sc-12345`),
  internal URLs, reporter identity or credentials. Describe the configuration
  instead; local notes may keep the IDs.
- **Precedence.** These rules first, then the repository's own `AGENTS.md` or
  `CLAUDE.md`, then the toolkit's skills.
