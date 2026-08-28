# Cherry-Pick Gate

Decides whether a change should be cherry-picked at all and selects the stable
scope-audit route used after application.

Consumes investigation output and produces the go/no-go decision plus tier classification.

## Inputs

- Investigation output (source analysis, target compat, prereq scan)
- `--force` flag (if set by user)

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

- **Without `--force`**: Stop. Explain why this change is not suitable. List which reject criteria it hits. Suggest alternatives (e.g., "consider a targeted rewrite on the target branch instead").
- **With `--force`**: Warn explicitly what reject criteria are being overridden, then continue. The warning must appear in the final report. Force does not skip any downstream phase — it only overrides the accept/reject gate.

### Bug fixes

When the change is a bug fix:

- Consume the existing-fix status from the investigation output (investigate already ran `debug/references/check-existing-fix.md` — do not re-run it).
- `Status: FIXED_UPSTREAM` with high confidence → stop, the fix is already there.
- `Status: FIX_PENDING_PR` → proceed with the backport and record the pending PR in the row/final report (a pending master PR doesn't reach a release branch by itself); `--step` restores the wait-or-proceed ask.
- `Status: UNFIXED` or `SKIPPED` → continue to the target-affected check below.

Then consume the **target-affected** verdict (the "is the bug even live on target" scan — distinct from existing-fix's "is the fix already here"). This is the gate that *produces* the "master-only regression" Skip; without it that skip only happens by luck:

- `Target-affected: NOT_AFFECTED` (concrete evidence — a named introducing commit not on target, or the buggy code path demonstrably absent) → **SKIP**. Verdict `SKIP`, reason `target not affected — <commit/path> not present on <target>`. Do not backport a fix for a bug that can't occur.
- `Target-affected: UNCLEAR` → proceed, but record the open applicability question on the row so the final report carries it. Never skip on absence of evidence.
- `Target-affected: AFFECTED` → continue. A live bug whose fix won't apply stays AFFECTED and becomes Blocked/Partial in apply — that is not a skip here.

### Features with `--force`

When force-cherry-picking a feature, additionally flag:
- Dependency additions the target branch doesn't have
- API surface changes that may break consumers
- Whether the feature requires follow-up work on the target branch

These are warnings, not blockers.

## Difficulty Classification

After the go/no-go decision, classify the change against
`rules/complexity-gate.md`'s three-tier vocabulary (the same
TRIVIAL/STANDARD/COMPLEX every other goal skill uses — cherry-pick's own
signals below select the tier, but the tier names and their downstream
consequences, review vs deep-review, are shared, not skill-local):

| Signal | TRIVIAL | STANDARD | COMPLEX |
|--------|---------|----------|---------|
| Files touched | 1–2 | 3+, one coherent change | 3+, spanning components |
| Change type | Version bump, config, import fix, one-liner | Logic change, well-understood pattern | Behavioral, multi-component, or architectural |
| Conflicts expected | None (clean apply likely) | Conflicts expected or detected, resolvable | Conflicts entangled with modify/delete or scope leak risk |
| Dependencies | No new dependencies | No new dependencies | Adds/changes dependencies |
| Target compatibility | APIs and modules exist and match | APIs and modules exist and match | APIs differ, modules missing or renamed |
| Prerequisite commits | None needed | None needed | Prerequisites identified |

Classify as **TRIVIAL** only when ALL trivial signals apply. Any single
non-trivial signal makes the change at least **STANDARD**. Any Forced
Complex Escalation trigger below makes it **COMPLEX** regardless of the
table.

## Forced Complex Escalation

Regardless of signals, classify as **COMPLEX** when:

- `--force` is overriding a reject-category change
- Investigation flagged modify/delete risk
- Investigation flagged prerequisite commits
- The change is a bundled PR with multiple sub-fixes
- Dependency manifests or lockfiles are touched

## Output

```markdown
## Gate Decision

Verdict: PROCEED / REJECT / FORCE-PROCEED / SKIP
Difficulty: TRIVIAL / STANDARD / COMPLEX
Reject Criteria Hit: [list or "none"]
Skip Reason: [e.g. "target not affected — <commit/path> not on <target>", or "none"]
Force Override: YES / NO

### Worker Route
Scope Audit: review / deep-review
Adapt Required: YES / NO
```

## Worker Route Selection

| Phase | TRIVIAL | STANDARD | COMPLEX |
|-------|---------|----------|---------|
| Plan | Main thread | Main thread | Main thread |
| Apply | Main thread | Main thread | Main thread |
| Adapt | skipped | Main thread | Main thread |
| Scope-leak audit | `review` | `review` | `deep-review` |
| Correctness validation | Main thread | Main thread | Main thread |

The route names above are stable. Their exact selectors and `high`/`xhigh`
effort values come only from `interfaces/model-routing.json`.
