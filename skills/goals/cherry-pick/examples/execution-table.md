# Execution Table Format (Full)

The 13-column table tracks each cherry through every phase. Produced by the plan phase, updated by apply/adapt/validate, preserved through the final report as detailed notes.

For large runs, the full table belongs in local `CHERRY_PICK.md` using [../templates/cherry-pick-manifest.md](../templates/cherry-pick-manifest.md). The final report should use the compact table from [final-report.md](final-report.md) and link back to the local manifest for detailed audit context. Chat should not become the durable store for every row, log, and handoff.

```markdown
| # | SHA | PR | Description | Depends On | Risk | Confidence | Decision | Status | Adaptation | Scope Audit | Validation | Notes |
|---|-----|----|-------------|------------|------|------------|----------|--------|------------|-------------|------------|-------|
| 1 | `<sha>` | #123 | <summary> | — | LOW | 9/10 | Auto | Applied | None | CLEAN | Tested | Clean apply |
| 2 | `<sha>` | #124 | <summary> | #123 | MED | 7/10 | Approval | Partial | Medium | CLEAN (1 hunk reverted) | Checked | 2 of 3 sub-fixes applied |
```

## Field Meanings

| Field | Values | Populated by |
|-------|--------|--------------|
| `#` | Order in batch (1-based) | batch-sequence |
| `SHA` | Short commit sha | investigate |
| `PR` | `#NNN` or `—` | investigate |
| `Description` | One-line summary | investigate |
| `Depends On` | Other `#` or `—` | batch-sequence |
| `Risk` | `LOW`, `MED`, `HIGH` | gate |
| `Confidence` | `X/10` | gate |
| `Decision` | `Auto`, `Approval`, `Escalate` | gate |
| `Status` | `Planned`, `Applied`, `Partial`, `Blocked`, `Rejected`, `Skipped` | apply/adapt |
| `Adaptation` | `None`, `Minor`, `Medium`, `High` | adapt (see plan.md for definitions) |
| `Scope Audit` | `CLEAN`, `CLEAN (N hunks reverted)`, `ESCALATE` | scope-leak subagent (7a) |
| `Validation` | `Not run`, `Tested`, `Checked`, `Build-only`, `Structural` | validate (7b, main thread) |
| `Notes` | Short freeform | any phase |

## Scope Audit Field

**Mandatory.** A cherry cannot be marked `Applied` (or `Partial`) without a `Scope Audit` value populated by the scope-leak subagent (see [../references/validate.md](../references/validate.md)). The literal `scope-audit.sh` output and per-hunk verdict belong in the detailed notes for any row whose audit was not pristine `CLEAN`.

## Status Semantics

- **Planned** — plan produced, not yet applied
- **Applied** — cherry-pick landed on target with or without adaptation
- **Partial** — applied but significant portions dropped. **Always requires detailed notes**.
- **Blocked** — cannot proceed (prerequisite missing, unresolvable conflict)
- **Rejected** — gate rejected, no `--force` supplied
- **Skipped** — duplicate of an existing fix, or explicitly skipped by user

## Validation Semantics

See [../references/validate.md](../references/validate.md) for the authoritative label definitions and failure-handling table. Never use "Clean" or "Validated" — they are ambiguous.
