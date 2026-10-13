# Cherry-Pick Run

Target branch:
Source branch:
Created:
Policy:

**Rule:** this file is the only row schema for a cherry-pick run. Rows ≤3 lines
per cell. No diffs, raw logs, or worker transcripts: only PR/SHA refs,
one-line outcomes and decisive short excerpts.

## Current Batch

Wave:
Status:
Next action:

## Batch Pre-Flight

Rows from `scripts/batch-preflight.sh <target> <pr or sha>...` ([batch.md](../references/batch.md)).

| Status | Request | PR | SHA | Parents | Evidence | Title |
|--------|---------|----|-----|--------:|----------|-------|
| NEEDS_INVESTIGATION |  |  |  |  |  |  |

## Execution Waves

| Wave | PR/SHA | Depends On | Risk | Status | Notes |
|------|--------|------------|------|--------|-------|
| 1 |  |  |  | Planned |  |

## Execution Table

| Order | PR | Source SHA | Result | Target SHA | Scope Audit | Validation | Push | Adaptation | Owner-notified | Commands | Notes |
|------:|----|------------|--------|------------|-------------|------------|------|------------|----------------|----------|-------|
| 1 |  |  | Planned |  |  | Not run |  |  |  |  |  |

- **Result:** `Planned` (plan produced, not applied); `Applied` (landed on the
  target, with or without adaptation); `Partial` (applied with significant
  parts dropped; always needs a Notes entry); `Blocked` (cannot proceed:
  missing prerequisite, unresolvable conflict); `Rejected` (the gate rejected
  it and no `--force` was given); `Skipped` (already applied, not affected, not
  merged, or skipped by the user).
- **Scope Audit:** `CLEAN`, `LEAKED-REVERTED` or `ESCALATED`. Required before
  `Applied` or `Partial`; a `Blocked`, `Rejected` or `Skipped` row may leave
  it empty.
- **Validation:** the labels in [validate.md](../references/validate.md).
- **Push:** `pushed <sha>`, `pending-authorization` or `deferred` (SKILL.md,
  Per-Cherry Push).
- **Adaptation:** the severity, plus one line on what changed from the source.
  `None`: applied mechanically, no conflict resolution. `Minor`: import paths,
  renamed variables, or trivial API differences. `Medium`: logic rewritten to
  fit target-side APIs, or a functional subset extracted from a mixed commit.
  `High`: significant chunks dropped (functions, files or bug fixes) because
  the target lacks required architecture; requires user awareness, always
  with a Notes entry.
- **Owner-notified:** `n/a`, or the story comment link
  ([blocked-owner-comment.md](../references/blocked-owner-comment.md)).

## Blocked / User Decisions

| PR/SHA | Decision needed | Options | Recommendation |
|--------|-----------------|---------|----------------|
|  |  |  |  |

## Subagent Handoffs

Each per-cherry or per-wave worker returns only this block; no full diffs or
long logs unless blocked.

### PR/SHA

- Result:
- Source commit(s):
- Target SHA:
- Conflicts:
- Scope audit:
- Validation:
- Push:
- Commands run:
- Residual risk:
- Dependency implications:
- Unblock candidates (Blocked/Rejected only):
