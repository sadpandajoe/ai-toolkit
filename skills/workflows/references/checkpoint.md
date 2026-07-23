# Save Workflow State

> **When**: Anytime you want to update PROJECT.md state — saving resume context before `context_reset`, ending the session, or just logging progress mid-workflow.
> **Produces**: Continuation Checkpoint + Current Status refresh + optional Progress Update entry in PROJECT.md.

## Effect Boundary

Effect: `local_mutation`.

This is the single command for updating PROJECT.md state. It absorbed the older `/update-project-file` — for quick progress logs, use `checkpoint "message"`.

## Usage

```
checkpoint                                        # Write checkpoint + refresh status (no log entry)
checkpoint "completed auth module, on to tests"   # Same + append a Progress Update entry
checkpoint + context_reset                                # Write, then context_reset
checkpoint --quit                                 # Write, then quit the session
checkpoint "msg" --clear                          # Write with log entry, then context_reset
checkpoint "msg" --phase implement --target "PR #42"  # Override autodetected fields
```

**Flags:**
- `--clear` — Write, then request a context clear (the model cannot invoke `context_reset`; see step 3).
- `--quit` — Quit the session after writing (falls back to printing "Run /quit to exit." if programmatic quit isn't available).

**Positional argument (optional):** a short message describing what just happened or where you left off. Becomes the "Where we left off" line in a Progress Update entry.

**Named overrides (optional):**
- `--phase <phase>` — override autodetected phase
- `--target "<text>"` — override autodetected "Where we left off" text
- `--learnings "<note>"` — explicit learnings (otherwise auto-detect from conversation if obvious)

## Steps

### 1. Identify Current State

Read the conversation context and PROJECT.md (if it exists) to determine:
- **Top-level command**: the user-facing command in progress (e.g., `create-feature`, `fix-bug`) or `none` for ad-hoc work
- **Phase**: current internal phase (e.g., `plan-mode`, `implement`, `review-code`) or `ad-hoc`
- **Active plan**: `PLAN.md` if one exists at repo root, otherwise `none`
- **Where we left off**: the next concrete action — file + line context, ticket, or specific item to pick up
- **Done / In Progress / Next / Blocked** for the Current Status block
- If the active phase is `review-code`, read the `## Current Code Review` section in PROJECT.md if present and preserve its next finding/fix action in Current Status.

If positional/named arguments were provided, use them instead of autodetecting.

### 2. Write to PROJECT.md

The three templates below are the canonical format — other commands and [reporting templates](../../reporting/SKILL.md) reference them and should not duplicate them. Write or update three sections (creating PROJECT.md if it doesn't exist):

**a. `## Continuation Checkpoint` — overwrite (only one exists at a time):**

The checkpoint header is intentionally light — workflow metadata only. State details live in Current Status; resume specifics live in the Progress Update message. Do not duplicate across sections.

Start from the generic shape:

```markdown
## Continuation Checkpoint — [ISO timestamp]
### Workflow
- Top-level command: [command or "none — ad-hoc work"]
- Phase: [phase]
- Active plan: PLAN.md | none
```

If the detected top-level workflow has a per-workflow extension at `skills/reporting/templates/<command>-checkpoint.md` (e.g. `fix-bug-checkpoint.md`, `create-feature-checkpoint.md`), append the additional Workflow fields that template specifies. The per-workflow templates own only the extra fields — they do not redefine the generic header. For ad-hoc work or commands without an extension, write the generic shape alone.

**b. `## Current Status` — refresh in place:**

```markdown
## Current Status

**Done:**
- [x] [completed items]

**In Progress:**
- [ ] [current work]

**Next:** [upcoming task or "none"]
**Blocked:** [blocker or "none"]
```

When a previously-In-Progress item completes, move it to Done. When Next becomes the new focus, move it to In Progress.

If PROJECT.md contains `## Current Code Review`, keep it intact unless the Review Gate is clean and the caller workflow has moved past review. Do not collapse review findings into chat-only summary text before `context_reset`.

**c. `### [timestamp] — Progress Update` — append to Development Log:**

Only write this section if a positional message was provided OR a learning was detected.

```markdown
### [ISO timestamp] — Progress Update
**Where we left off:** [the message arg, or autodetected resume context]
**Learnings:** [optional — observations worth capturing for future rule/command/skill updates]
```

The Learnings field is for things you noticed during work that should inform later improvements (rule updates, skill changes, common pitfalls). Skip the field if there's nothing to capture.

### 3. Run `--clear` or `--quit` (if specified)

- `--clear`: `context_reset` is a built-in only the user can run — there is no programmatic clear. After writing, end the turn with exactly: `Checkpoint saved. Run context_reset, then start to resume.` `start` reads the checkpoint and continues the saved workflow. Do not start new work after emitting this line — the turn is over.
- `--quit`: invoke `/quit` if available; otherwise emit `"Checkpoint saved. Run /quit to exit."` as the final message and stop.

Skip both if neither flag was specified.

---

This command does not resume. `start` handles that — it reads the Continuation Checkpoint and auto-continues the saved workflow.

For STANDARD or expensive workflows, callers should use checkpoint + context_reset at major phase boundaries after durable artifacts are current. This is proactive token control, not only an emergency response to full context.
