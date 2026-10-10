# Project Capstone

> **When**: A project or major body of work is complete and you want to summarize, promote learnings, archive, and hand off.
> **Produces**: Project-level metrics summary, promoted/pruned memories, archived PROJECT.md, and a recommended final action.

## Effect Boundary

Effect: `local_mutation`.

This is the bookend to `start` — it closes what `start` opens.

## Usage

```
complete-project                    # Full capstone for current project
complete-project --skip-promote     # Skip the memory promotion step
```

## Goal

Close a finished project: summarize what it did, settle its learnings, archive
its state, release its local services with the user's consent, and hand off
the next action. The run is complete when the archive holds the completed
phases, PROJECT.md holds the final status, and the summary and metrics event
are emitted.

## Steps

1. **Read the project.** Read PROJECT.md completely for the goal, what was
   built or fixed, key decisions, open risks, and branch state (`git log
   --oneline -20`, `git status`, current branch). With no PROJECT.md, stop:
   `No PROJECT.md found. This command requires an active project file.`
2. **Summarize metrics** for this project with `bin/aitk metrics --since
   <project start> --format project`; it prints `No metrics recorded for this
   project` when nothing matches, and the run continues.
3. **Review the observation queue** (skipped with `--skip-promote`). When
   `.ai-toolkit/observations.jsonl` has unreviewed lines, run the *Review*
   section of [skills/reflection/references/observations.md](../../reflection/references/observations.md)
   (`reflect observations`): `bin/aitk lane-yield` first, then cluster the
   lines and present proposals. Apply only on confirmation and move reviewed
   lines to `.ai-toolkit/observations.reviewed.jsonl`. This is the one point
   in a project where the queue is guaranteed to be read, so an empty queue is
   reported as `No unreviewed observations` rather than skipped silently.
4. **Surface memory promotion candidates** (skipped with `--skip-promote`).
   From the project memory directory, pick feedback memories that apply
   across projects, postmortems (`feedback_failure_*`) whose prevention points
   to a universal rule or skill change, and themes several memories share.
   Present each:

   ```markdown
   ### Promotion Candidate: {filename}
   **Pattern**: {one-line summary}
   **Why promote**: {reasoning}
   **Suggested action**: Promote to rule / Keep as memory / Prune (outdated)
   ```

   Wait for the user's answer on each. **Promote** runs `reflect promote`
   with that approval as pre-authorization: it drafts and writes the rule,
   deletes the source memory, and updates MEMORY.md without re-asking intent
   (standalone `reflect promote` keeps its own rule-text confirmation).
   **Prune** deletes the memory file and its MEMORY.md entry. **Keep** does
   nothing.
5. **Archive** every completed phase, not just the latest, by running
   `archive-project-file` as an internal phase through the
   [archive skill](../../archive-project-file/SKILL.md).
6. **Tear down branch-local services, with one confirmation.** Collect the
   candidates: containers whose names or labels match the branch, project
   name, or working directory
   (`docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'`); a running
   Compose stack when a `docker-compose.yml` or `compose.yml` exists
   (`docker compose ps`); dev servers rooted in this project directory on the
   common ports (`lsof -ti :<common-ports>` for 3000, 3001, 5173, 8080, 8088);
   and project worktrees with no uncommitted changes (`git worktree list`).
   List them and ask once which to stop or remove; act only on the confirmed
   set, and report it:

   ```markdown
   ### Services Torn Down
   - [service]: [action taken]
   ```

   When nothing is running, skip this step silently.
7. **Write the final status** with
   [skills/reporting/templates/complete-project-final.md](../../reporting/templates/complete-project-final.md),
   replacing the prior status section.
8. **Suggest the next action** from the branch state: uncommitted changes →
   commit, then `create-pr`; committed with no PR → `create-pr`; PR open →
   review and merge, then deploy; everything merged → deploy to staging or
   production; no code changes → nothing further. Merging and deploying are
   the user's actions; suggest them, never run them.
9. **Summarize and record metrics.** Use
   [skills/reporting/templates/complete-project-summary.md](../../reporting/templates/complete-project-summary.md)
   under the structural rules in [skills/reporting/SKILL.md](../../reporting/SKILL.md),
   then record metrics with `bin/aitk metrics emit --workflow
   complete-project --status <clean | blocked>` (`blocked` when step 6 left
   services running, and similar), passing the memory-promotion decisions as
   `--extra 'decisions={…}'` and worker counts as `--workers`.
