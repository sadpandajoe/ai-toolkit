# Initialize Session

> **When**: Beginning any work session; the only entrypoint for resuming work in a fresh session.
> **Produces**: Loaded PROJECT.md context and a session entry.

## Effect Boundary

Effect: `local_mutation`.

## Steps

1. **Read the state.** `bin/aitk project-state show` finds PROJECT.md (the
   working directory, then the git repository root, symlinks resolved) and
   prints the routing snapshot. Read PROJECT.md through a symlink, but write
   to its `readlink -f` target, as for PLAN.md: an editor tool may refuse to
   write through the link. When none exists, create one from the
   repository-root [PROJECT_TEMPLATE.md](../../../PROJECT_TEMPLATE.md) and say
   so in the session entry (it is local-only); with `--ask`, ask first.

2. **Resume an unfinished workflow** from the snapshot, at its
   `current_phase` and `current_gate`, without asking. If the snapshot's
   complexity predates v2 (a legacy three-tier value), re-run the Complexity
   Gate and record it first. Append:

   ```markdown
   ### [Timestamp] - Session Resumed
   - Branch: [current branch]
   - Workflow: [workflow] at [phase] / [gate]
   - Resume target: [Next from Current Status]
   ```

   For MULTI_PHASE work, add the remaining phases:

   ```markdown
   ### Remaining Phases
   Done: <phases marked done>
   Active: <phase> (<complexity>/<size>)
   Ahead: <pending phases>
   Next gate: <gate> — <what PASS requires>
   ```

   The resumed workflow loads its own rules and skills. PLAN.md is read only
   when the next phase needs it (review iterations or an implementation
   slice), so status checks stay light.

3. **Otherwise start a session.** Append:

   ```markdown
   ### [Timestamp] - Session Start
   - Branch: [current branch]
   - Status: [summary from Current Status]
   - Goal: [the user's goal, once stated]
   ```

   Ask what the user wants to work on, and suggest the matching workflow from
   `<toolkit-root>/bin/aitk list`; suggest `reflect observations` when the
   observation-reminder hook reports a backlog.

4. **Nudge toward archiving.** When PROJECT.md holds `Completed: <date> —
   <feature>` entries, or a `PLAN.md` sits at the repository root with no
   unfinished workflow in the snapshot, say so before any workflow
   suggestion: how many completed phases, whether a stale PLAN.md is present,
   and that `archive-project-file` cleans them up. Long logs of finished work
   or resolved blockers in active sections earn a brief mention only next to
   one of those signals. Recommend, never auto-run: `archive-project-file` is
   the only deletion path.
