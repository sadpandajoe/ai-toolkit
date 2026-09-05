# Phase Handoff

Compact input and output for one phase of MULTI_PHASE or BATCHED work. The
parent fills the input from `PLAN.md` and the routing snapshot; the worker
returns the output; the parent records the checkpoint.

## Input (into the worker)

```markdown
## Phase Handoff: <phase or wave>
Snapshot: <workflow> <complexity>/<size>/<shape>; phase <n> of <total>
Global invariants: <list from the decomposition>
Accepted phase plan: <verbatim slice or wave excerpt>
Scope: <files in; files out>
Exit criteria: <observable conditions>
Acceptance: <exact command>
Prior phase learnings: <constraints discovered, or none>
```

## Output (back to the parent)

The worker returns `## Handoff: <role>` from `rules/specialist-handoff.md`.

## Checkpoint (parent writes to PROJECT.md)

```markdown
## Phase Complete: <phase or wave>
Exit criteria: <met — evidence>
Learned constraints: <list, or none>
Invariant changes: <none, or RECLASSIFY recorded>
Evidence: <verification gate reference>
Next phase: <name, reclassified as <complexity>/<size>, or "done">
```

Then `bin/aitk project-state phase --name <phase> --status done` and, for the
next phase, `--status active` after its plan is written.
