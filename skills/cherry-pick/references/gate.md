# Cherry-Pick Gate

Decides whether a change should be cherry-picked at all and classifies its
difficulty. Consumes the investigation output and any `--force` flag.

## Decision: Should We Cherry?

Evaluate the change against the accept/reject matrix:

| Accept | Reject |
|--------|--------|
| Bug fixes | Architecture changes |
| Isolated features | Unverified imports |
| Algorithm improvements | Breaking API changes |
| Test additions | Build system changes |
| Documentation | File restructuring |

### Reject-category changes

- **Without `--force`**: stop, list the reject criteria it hits, and suggest an alternative (e.g., a targeted rewrite on the target branch).
- **With `--force`**: warn which reject criteria are overridden, carry the warning into the final report, and continue. Force skips no downstream phase.

### Bug fixes

- Consume the existing-fix status from the investigation output; do not re-run `debug/references/check-existing-fix.md`.
- `Status: FIXED_UPSTREAM` with high confidence → stop, the fix is already there.
- `Status: FIX_PENDING_PR` → proceed with the backport and record the pending PR in the row/final report (a pending master PR doesn't reach a release branch by itself); `--step` restores the wait-or-proceed ask.
- `Status: UNFIXED` or `SKIPPED` → continue to the target-affected check below.

Then consume the **target-affected** verdict ("is the bug even live on target", distinct from "is the fix already here"); it is what produces the master-only-regression skip:

- `Target-affected: NOT_AFFECTED` (concrete evidence — a named introducing commit not on target, or the buggy code path demonstrably absent) → **SKIP**. Verdict `SKIP`, reason `target not affected — <commit/path> not present on <target>`. Do not backport a fix for a bug that can't occur.
- `Target-affected: UNCLEAR` → proceed, but record the open applicability question on the row so the final report carries it. Never skip on absence of evidence.
- `Target-affected: AFFECTED` → continue. A live bug whose fix won't apply stays AFFECTED and becomes Blocked/Partial in apply — that is not a skip here.

### Features with `--force`

Flag, as warnings rather than blockers: dependency additions the target lacks, API surface changes that may break consumers, and follow-up work the feature needs on the target.

## Difficulty Classification

**TRIVIAL** means: clean apply expected, no API or module drift, no
prerequisite, no dependency manifest. Anything else is **NON-TRIVIAL**; file
count is not a signal (`rules/complexity-gate.md`).

## Forced Non-Trivial Escalation

Regardless of signals, classify as **non-trivial** when:

- `--force` is overriding a reject-category change
- Investigation flagged modify/delete risk
- Investigation flagged prerequisite commits
- The change is a bundled PR with multiple sub-fixes
- Dependency manifests or lockfiles are touched

## Output

```markdown
## Gate Decision

Verdict: PROCEED / REJECT / FORCE-PROCEED / SKIP
Difficulty: TRIVIAL / NON-TRIVIAL
Reject Criteria Hit: [list or "none"]
Skip Reason: [e.g. "target not affected — <commit/path> not on <target>", or "none"]
Force Override: YES / NO
Adapt Required: YES / NO
```

Leak audit: the parent runs `scope-audit.sh` on every cherry; the LLM audit
runs on `review` when the script flags something or conflicts were resolved,
and on `deep-review` only after an ESCALATE ([validate.md](validate.md)).
