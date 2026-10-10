# Initialize Session

Use the repository-root [PROJECT_TEMPLATE.md](../../../PROJECT_TEMPLATE.md) when a new durable state file is required.

> **When**: Beginning any work session.
> **Produces**: Loaded PROJECT.md context and session entry.

## Effect Boundary

Effect: `local_mutation`.

This command is the only supported entrypoint for resuming work in a fresh session.
It restores workflow state from PROJECT.md (routing snapshot plus checkpoint) rather than relying on chat memory.

## Steps

1. **Find and read PROJECT.md**: the working directory first, then the git
   repo root, then any additional working directories. A symlinked PROJECT.md
   is normal: read through it, and write to the resolved path (`readlink -f`),
   as for PLAN.md and every toolkit-managed file. When none exists, create one
   from `PROJECT_TEMPLATE.md` and say so in the session entry (it is
   local-only); with `--ask`, ask before creating it.

2. **Resume when PROJECT.md has a `## Continuation Checkpoint`.** Resume at
   the routing snapshot's `current_phase` and `current_gate`
   (`bin/aitk project-state show`); the checkpoint names the workflow, active
   plan, and resume target. If the snapshot is missing or its complexity
   vocabulary predates v2 (a legacy three-tier value), re-run the Complexity
   Gate and record it before continuing. Append a session entry:

   ```markdown
   ### [Timestamp] - Session Resumed
   - Branch: [current branch]
   - Resuming from: [checkpoint timestamp]
   - Command: [top-level workflow from checkpoint]
   - Phase: [saved phase]
   - Active plan: [PLAN.md or none]
   - Resume target: [saved item or iteration]
   ```

   For MULTI_PHASE work, add the remaining phases:

   ```markdown
   ### Remaining Phases
   Done: <phases marked done>
   Active: <phase> (<complexity>/<size>)
   Ahead: <pending phases>
   Next gate: <gate> — <what PASS requires>
   ```

   Then continue the saved workflow without asking. It loads its own rules,
   skills, and supporting files, and PLAN.md is read only when the next phase
   needs it (review iterations or an implementation slice), so status checks
   stay light. Once the resume succeeds, replace the human `## Continuation
   Checkpoint` section so the same state is not resumed twice; the machine
   block changes only through `bin/aitk checkpoint`.

3. **Otherwise start a session.** Append:

   ```markdown
   ### [Timestamp] - Session Start
   - Branch: [current branch]
   - Status: [summary from Current Status]
   - Goal: [the user's goal, once stated]
   ```

   Ask what the user wants to work on. When they state a goal, suggest the
   matching workflow from `<toolkit-root>/bin/aitk list`; suggest
   `reflect observations` when the observation-reminder hook reports a
   backlog in `.ai-toolkit/observations.jsonl`.

4. **Recommend Archiving When Useful**

   Run these checks against PROJECT.md and the repo root:

   **Concrete signals** (high-confidence — surface the suggestion explicitly):
   - PROJECT.md contains one or more `Completed: <date> — <feature>` entries (workflow finished, content not yet archived)
   - A stale `PLAN.md` exists at the repo root with no Continuation Checkpoint pointing to it (workflow finished but the plan file still sits there)

   **Soft signals** (lower-confidence — mention only if a concrete signal already fired):
   - Long Development Log sections for work already complete
   - Resolved blockers still in active sections
   - Active work becoming hard to find

   If any **concrete signal** fires, put the suggestion before any next-command suggestion: name the number of completed phases found, whether a stale PLAN.md is present, and that `archive-project-file` cleans them up before the next major phase.

   If only soft signals fire, mention briefly at the end of the session entry.

   Always recommend, never auto-run. `archive-project-file` is the only deletion path; workflows do not auto-delete.
