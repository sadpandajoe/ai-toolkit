# Stop Rules

Universal stop conditions for iterative review and fix loops.

## When to Stop

Stop the current loop when any of these are true:

- **Only nitpicks remain** — no `[major]` or `[minor]` findings left (severity definitions in `rules/severity.md`)
- **A user decision is required** — a design trade-off, scope question, or ambiguity that only the user can resolve (e.g., "should we extract a helper or keep inline?", "should we add missing docs or defer?")
- **Same issue persists across two consecutive rounds** — the fix attempt did not resolve it; further iteration will not help

## What "Stop" Means

"Stop" means emit the Review Gate block per `rules/review-gate.md` with the appropriate Status:
- Only nitpicks remain → `Status: clean`
- User decision needed → `Status: user decision`
- Same issue persists → `Status: blocked`

Then hand control back to the calling workflow. "Stop" does not mean abandon
the workflow; the caller owns next steps (commit, summary, handoff). See the
Continuation Rule in `rules/review-gate.md`.

## Scope

This rule applies to review/fix loops (`review/references/code-quality.md`), plan
review iterations, and any other iterative quality loop. It does not override
stricter workflow-specific stop conditions.
