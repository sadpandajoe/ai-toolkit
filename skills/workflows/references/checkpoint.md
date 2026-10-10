# Save Workflow State

> **When**: Anytime you want to update PROJECT.md state — before handing a phase to a fresh worker, ending the session, or just logging progress mid-workflow.
> **Produces**: Continuation Checkpoint + Current Status refresh + optional Progress Update entry in PROJECT.md.

## Effect Boundary

Effect: `local_mutation`.

This is the single command for updating PROJECT.md state. For quick progress logs, use `checkpoint "message"`.

## Usage

```
checkpoint                                        # Write checkpoint + refresh status (no log entry)
checkpoint "completed auth module, on to tests"   # Same + append a Progress Update entry
checkpoint "msg" --clear                          # Write with log entry, then suggest a fresh session
checkpoint "msg" --phase implement --target "PR #42"  # Override autodetected fields
```

- A positional message becomes the "Where we left off" line of a Progress
  Update entry.
- `--phase <phase>` and `--target "<text>"` override the detected phase and
  "Where we left off" text; `--learnings "<note>"` records learnings
  explicitly instead of detecting them.
- `--clear`: after writing, end the turn with `Checkpoint saved. Start a fresh
  session and run start to resume.` and start no new work; `start` reads the
  snapshot and checkpoint and continues the saved workflow. Clearing is the
  user's optional hygiene, never a workflow requirement.

## What to Write

Take the top-level workflow and phase from the routing snapshot
(`bin/aitk project-state show`) when one exists, so the checkpoint agrees with
what `start` resumes. Without a snapshot, use the user-facing command in
progress (or `none — ad-hoc work`) and a phase from its contract in
`interfaces/contracts.json` (such as `plan`, `implement`, or `review`), or
`ad-hoc`. The active plan is `PLAN.md` when one exists at the repo root.
"Where we left off" is the next concrete action: file and line, ticket, or
the item to pick up. When PROJECT.md has a `## Current Code Review` section,
keep it intact until the review gate is `PASS` and the caller has moved past
review, and carry its next finding or fix into Current Status rather than
collapsing it into chat.

The three templates below are the canonical format; other commands and
[reporting templates](../../reporting/SKILL.md) reference them and should not
duplicate them. Create PROJECT.md if it does not exist.

**a. `## Continuation Checkpoint`: overwrite (only one exists at a time).**
It carries workflow metadata only; state lives in Current Status and resume
specifics in the Progress Update.

```markdown
## Continuation Checkpoint — [ISO timestamp]
### Workflow
- Top-level command: [command or "none — ad-hoc work"]
- Phase: [phase]
- Active plan: PLAN.md | none
```

When the workflow has an extension at
`skills/reporting/templates/<command>-checkpoint.md` (e.g.
`fix-bug-checkpoint.md`), append the extra Workflow fields it specifies;
extensions never redefine this header.

**b. `## Current Status`: refresh in place.**

```markdown
## Current Status

**Done:**
- [x] [completed items]

**In Progress:**
- [ ] [current work]

**Next:** [upcoming task or "none"]
**Blocked:** [blocker or "none"]
```

**c. `### [timestamp] — Progress Update`: append to the Development Log** only
when a positional message was given or a learning is worth keeping.

```markdown
### [ISO timestamp] — Progress Update
**Where we left off:** [the message arg, or autodetected resume context]
**Learnings:** [optional — observations worth capturing for future rule/command/skill updates]
```

Learnings are things noticed during the work that should inform later rule,
skill, or command changes; omit the field when there are none.

---

This command does not resume. `start` handles that — it reads the Continuation Checkpoint and auto-continues the saved workflow.

Callers checkpoint at every phase boundary after durable artifacts are current, then hand the next phase to a fresh worker. Fresh workers, not manual clears, are the context boundary (`rules/context-management.md`).
