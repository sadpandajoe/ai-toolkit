# Save Workflow State

> **When**: Anytime you want to update PROJECT.md state — before handing a phase to a fresh worker, ending the session, or just logging progress mid-workflow.
> **Produces**: A Current Status refresh and an optional Progress Update entry in PROJECT.md.

## Effect Boundary

Effect: `local_mutation`.

## Usage

```
checkpoint                                        # Refresh Current Status
checkpoint "completed auth module, on to tests"   # Same + append a Progress Update entry
checkpoint "msg" --phase implement --target "PR #42"  # Override detected fields
checkpoint "msg" --clear                          # Write, then end the session
```

`--learnings "<note>"` records learnings explicitly. `--clear` follows the
provider's `context_reset` binding once the state is written: end the turn with
`Checkpoint saved. Start a fresh session and run start to resume.` and start
no new work. Clearing is the user's optional hygiene, never a workflow
requirement.

## What to Write

The workflow and phase come from `bin/aitk project-state show`, the record
`start` resumes from; `bin/aitk checkpoint` owns the machine block. Create
PROJECT.md if it does not exist. The model writes only Current Status, in
place:

```markdown
## Current Status

**Done:**
- [x] [completed items]

**In Progress:**
- [ ] [current work]

**Next:** [the next concrete action: file and line, ticket, or item]
**Blocked:** [blocker or "none"]
PR: <number> — <title>
Existing-fix status: FIXED_UPSTREAM | FIX_PENDING_PR | UNFIXED | SKIPPED | pending
```

`PR:` is for PR workflows and `Existing-fix status:` for `fix-bug`; omit
either when it does not apply. Append a Development Log entry only when a
message was given or a learning is worth keeping:

```markdown
### [ISO timestamp] — Progress Update
**Where we left off:** [the message, or the next concrete action]
**Learnings:** [optional: what should inform a later rule, skill, or command change]
```

`## Current Code Review` stays intact until the review gate is `PASS`; carry
its next finding into Current Status. This command does not resume; `start`
does.
