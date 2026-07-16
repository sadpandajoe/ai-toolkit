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

## Steps

### 1. Read PROJECT.md — Determine What Was Accomplished

Read PROJECT.md completely. Extract: goal, what was built or fixed, key decisions, open risks, branch state (`git log --oneline -20`, `git status`, current branch).

If no PROJECT.md exists, stop: `No PROJECT.md found. This command requires an active project file.`

### 2. Read Metrics — Project-Level Summary

Read `.ai-toolkit/metrics.jsonl` (falling back to legacy `.claude/metrics.jsonl` only when needed). Filter to events relevant to this project and aggregate using [skills/reporting/templates/complete-project-metrics.md](../../reporting/templates/complete-project-metrics.md).

If the file is missing or no events match, emit `No metrics recorded for this project` and continue.

### 3. Scan Memories — Surface Promotion Candidates

Skip if `--skip-promote` was passed.

Read all memory files in the project memory directory. Identify promotion candidates:
- **Feedback memories** describing patterns applicable across projects (not project-specific context)
- **Postmortem memories** (`feedback_failure_*`) where the prevention recommendation points to a universal rule or skill change
- **Recurring themes** — multiple memories pointing to the same underlying pattern

For each candidate, present:

```markdown
### Promotion Candidate: {filename}
**Pattern**: {one-line summary}
**Why promote**: {reasoning}
**Suggested action**: Promote to rule / Keep as memory / Prune (outdated)
```

Wait for user confirmation per candidate. Then follow the matching `reflect` flow:
- **Promote**: `reflect promote` with pre-authorization — the candidate approval above already authorizes the promotion, so the sub-flow drafts the rule, writes, deletes the source memory, and updates MEMORY.md without re-confirming intent (standalone `reflect promote` keeps its own rule-text confirmation)
- **Prune**: delete the memory file and MEMORY.md entry
- **Keep**: no action

### 4. Archive Completed Phases

Run `archive-project-file` via the [archive skill](../../archive-project-file/SKILL.md) as an internal phase. Hint that this is a full-project archive — all completed phases should move out, not just the most recent one.

### 5. Tear Down Branch-Local Services

Identify and stop services started for this branch:

1. **Docker containers** — `docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'`. Stop containers whose names/labels match the branch, project name, or working directory.
2. **Docker Compose stacks** — if a `docker-compose.yml` (or `compose.yml`) exists, run `docker compose ps`; if anything is up, `docker compose down`.
3. **Dev servers / background processes** — `lsof -ti :<common-ports>` (3000, 3001, 5173, 8080, 8088). For matches rooted in this project directory, ask before killing.
4. **Worktrees** — `git worktree list`. For project-related worktrees with no uncommitted changes, offer to remove.

Report what was found and stopped:

```markdown
### Services Torn Down
- [service]: [action taken]
```

If nothing is running, skip silently.

### 6. Write Final PROJECT.md Status

Use the template at [skills/reporting/templates/complete-project-final.md](../../reporting/templates/complete-project-final.md). Replaces the prior status section.

### 7. Suggest Final Action

Pick one based on branch state:
- **Uncommitted changes**: commit, then `create-pr`
- **Changes committed, no PR**: `create-pr`
- **PR open**: merge, then deploy
- **Everything merged**: deploy to staging/production
- **No code changes (process/learning project)**: archive complete, no further action

### 8. Summary + Record Metrics

Use the summary template at [skills/reporting/templates/complete-project-summary.md](../../reporting/templates/complete-project-summary.md) following the structural rules in [skills/reporting/SKILL.md](../../reporting/SKILL.md).

After emitting the summary, include `metrics-emit` context using the [metrics emitter](../../metrics-emit/SKILL.md) with:
- `command`: `complete-project`
- `complexity`: `standard`
- `status`: `clean` (or `blocked` if step 5 left services running, etc.)
- `rounds`: 0 (no review loop)
- `gate_decisions`: include any user decisions made during memory promotion
- `worker_usage`: subagent/worker invocation counts when applicable

### 9. Suggest Final Clear

The capstone is also a natural context boundary — the project is closed, durable state is archived, and the next thing the user does will be a fresh project or unrelated work. Suggest a clean slate:

```
Project closed. Run checkpoint + context_reset to start the next session fresh.
```

Do not auto-clear. The user may want to stay in-session to push the PR, deploy, or pick up the suggested final action from step 7.
