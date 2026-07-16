# Review Gate

Output contract for `review-code` and any workflow that invokes it. This defines the block format — it does not override how review findings are produced.

## Block Format

Every review phase must emit this block, even when the review loop is skipped:

```markdown
## Review Gate
Rounds: [N]
Pre-flight: pass / fail / skipped — [reason]
Status: clean / blocked / user decision / skipped / micro-fix
```

## Status Values

| Status | Meaning |
|--------|---------|
| `clean` | Only nitpicks remain; safe to proceed |
| `blocked` | Unresolved `[major]` or `[minor]` findings; cannot proceed |
| `user decision` | A trade-off or ambiguity requires human input |
| `skipped` | Zero-logic diff — see skip rule below |
| `micro-fix` | Trivial diff that passed all checks — see micro-fix rule below |

## Skip Rule

When the diff contains zero logic changes (formatting-only, lint-disable, import reorder, whitespace):
- Emit the block with `Status: skipped` and a reason
- No `review-code` invocation needed
- The skip applies to the review loop only — pre-flight checks still run if applicable

## Micro-Fix Rule

When ALL of these are true:
- Diff is 3 lines or fewer
- Pre-commit passes
- Relevant checks/tests pass
- Confidence is 10/10

Then:
- `review-code` may be collapsed to a single Review Gate block with `Status: micro-fix` and the diff inlined
- No iterative review loop needed

## Mandatory Emission

The Review Gate block must appear even when the review loop is skipped. Callers branch on this block — completing a review phase without emitting it is not sufficient.

## Continuation Rule

The Review Gate marks the completion of the review phase, not the end of the workflow. After a gate passes (Status: `clean` or `micro-fix`), the calling workflow must continue to its remaining steps — QA validation, commit, summary, etc. Do not treat a passing review gate as a signal to stop or ask the user whether to continue.
