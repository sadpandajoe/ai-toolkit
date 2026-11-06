---
name: handoff
description: Keep local working notes (PROJECT.md, PROJECT_ARCHIVE.md, PLAN.md) for work that spans sessions — resume where the last session stopped, checkpoint progress before a break, and archive or wrap up finished work. Use when the user says resume, pick up where we left off, checkpoint, save progress, wrap up, or archive the project. Do NOT use for one-session tasks, PR descriptions, or anything meant to be committed.
---

# Handoff

Durable state lives in files, not chat, so a fresh session (or one after
compaction) can continue from the files alone.

## The files

- `PROJECT.md`: goal, decisions, failed approaches, current status, a dated
  log. Freeform; [project-template.md](project-template.md) is the preferred
  starting layout.
- `PROJECT_ARCHIVE.md`: finished work moved out of PROJECT.md, append-only.
- `PLAN.md`: the active plan, when the work needed one.
- Skills keep their own notes the same way: `WATCH.md` (`watch-pr`),
  `CHERRY_PICK.md` (`cherry-pick`), `CI_FIX.md` (`fix-ci`).

Look for PROJECT.md in the working directory, then the git repository root.

**Never committed.** The git guard blocks commits of these files and of
`.ai-toolkit/`. Also keep them out of `git status`: append any missing entries
(`PROJECT.md`, `PROJECT_ARCHIVE.md`, `PLAN.md`, `WATCH.md`, `CHERRY_PICK.md`,
`CI_FIX.md`, `.ai-toolkit/`) to the file `git rev-parse --git-path
info/exclude` prints. In a linked worktree `.git` is a file, so the literal
`.git/info/exclude` is the wrong path.

**Symlinks.** These files are often symlinks into a notes directory. Read
through the link, but write to its `readlink -f` target: Claude Code's Write
and Edit refuse to write through a symlink.

## Resume and checkpoint

On resume, continue from **Next** in Current Status without asking. A
checkpoint rewrites Current Status in place (done, in progress, the next
concrete action, blockers) and adds a dated log entry only for a decision,
discovery or learning worth keeping.

## Archive and wrap up

- Move finished phases (completed investigations, failed solutions once one
  works, resolved blockers, old log entries) to the end of PROJECT_ARCHIVE.md,
  verbatim, under `## Archive: <phase> — <date>` with a short summary of goal,
  outcome, key commits and the decisions with their reasons. Never rewrite
  earlier archive entries.
- Leave a `## Previous Work` breadcrumb above Current Status in PROJECT.md:
  phase, completion date, 1–3 sentences, "See PROJECT_ARCHIVE.md".
- Never archive Current Status, active work, open blockers or what the next
  step needs.
- Delete a PLAN.md only when no work is active on it; move anything worth
  keeping into the archive entry first, since it was never committed.
- When wrapping up a whole project, offer to stop branch-local services:
  containers named or labelled for the branch or project, a running Compose
  stack, dev servers from this directory (ports 3000, 3001, 5173, 8080, 8088),
  and clean worktrees for the project. List them and ask once.
- End with the next action the branch state implies (commit, `create-pr`,
  review and merge, deploy). Merging and deploying are the user's to do.
