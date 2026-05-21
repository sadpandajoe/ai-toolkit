---
tier: Standard
---

# CI Fix Orchestration

Use after logs have been gathered and failures have been classified. The command owns the final decision, but this reference defines grouping, routing, safe-fix scope, and commit recommendation strategy.

## Classify and Group

The orchestrator classifies failures inline by default. Spawn a triage subagent only when:
- multiple independent failures need parallel analysis
- logs are very large (>500 lines) and need focused extraction
- the failure pattern is novel and benefits from isolated reasoning

For large CI runs, classify failures in parallel by job/log chunk. Each subagent receives only the relevant log path or excerpt plus the classification shape below. It returns a compact record; the main thread writes that record to `CI_FIX.md` and groups failures by root cause before any fix is attempted.

Expected classification shape:

```yaml
failures:
  - name: <failing job/step>
    root_cause: <hypothesis>
    fix: <narrow proposed change>
    verification: <how to verify locally>
    complexity: trivial | moderate | standard
    confidence: <0-10>
    ours: true | false
notes: <any cross-failure context>
```

Group failures before fixing:
- **One shared root cause** -> one fix path
- **Independent root causes** -> fix in waves, smallest/safest first
- **Pre-existing/flaky** -> exclude from fix path and record evidence

The main thread owns grouping and sequencing. Subagents classify; they do not decide final fix order.

## Complexity Routing

Not-our-failure fast path: if all classified failures are pre-existing or not caused by this branch, exit early with evidence and no fix/review cycle.

Evaluate each remaining failure:

| Signal | Trivial | Moderate | Standard |
|--------|---------|----------|----------|
| Failure pattern | Known-pattern, mechanical | Known-pattern but behavioral | Novel or mixed |
| Files touched | 1-2 | 2-4, single subsystem | 3+ or unclear scope |
| Fix type | Mechanical | Logic change, known pattern | Behavioral, cross-cutting |
| Verification | STRONG or PARTIAL available | STRONG or PARTIAL available | WEAK only |

Trivial path: apply, verify, emit/obtain Review Gate, update PROJECT.md, summarize.

Moderate path: plan inline, apply, verify, run `/review-code`, update PROJECT.md, summarize.

Standard path: update PROJECT.md, validate RCA when needed, run the Action Gate, then apply only if the gate allows it.

## RCA and Action Gate

Use RCA validation when:
- the failure is novel
- confidence is below auto-proceed threshold
- multiple plausible root causes exist
- the proposed fix changes behavior

Proceed automatically only when the Action Gate says the fix is low-risk, high-confidence, and sufficiently verifiable.

## Apply Safe Fixes

- Trivial path: orchestrator applies the proposed fix inline.
- Standard path: spawn a planning subagent when useful. The subagent returns a file-level fix plan and flags cross-cutting concerns. The orchestrator applies the plan.

Keep scope limited to the failing surface. If verification is weak or root cause is ambiguous, stop instead of widening scope.

## Commit Recommendation Strategy

For STRONG-verified trivial/moderate fixes with a clean Review Gate, the default flow creates a new commit on the current feature branch and pushes it. Amend, rebase, and force-push still require explicit user authorization for this run, and the push target must be the current feature branch on the expected remote. PARTIAL/WEAK verification and standard-path holds stay non-committing.

| Scenario | Action |
|----------|--------|
| Lint/style only, cherry-pick flow | Recommend amending into the breaking cherry-pick commit; ask before rebase/force-push |
| Lint/style only, single parent commit clear | Recommend amend; ask before force-push |
| Lint/style only, multiple parent commits | Recommend `style:` commit; ask before commit/push |
| Trivial code fix + STRONG verification | Recommend a new commit; ask before commit/push |
| Standard path or PARTIAL/WEAK verification | Stop before commit — present diagnosis and recommended next step |

Detecting cherry-pick flow: check `git log --grep="cherry picked from commit"` on recent branch commits. If cherry-picked commits are present, trace which one last touched the lint-failing files (`git log -- <file>` filtered to cherry-picked SHAs). That is the commit to amend into, not necessarily the latest.

Force-push is only permitted after explicit user authorization, only on the current feature branch, and never on main/master or shared branches.

Use fixup+autosquash when amending a non-tip commit:

```bash
git commit --fixup=<originating-sha>
git rebase --autosquash <base>
```

Pre-commit hook warning: when staging files for commit A's fixup, hooks stash unstaged changes (including commit B's fix) and run checks against the incomplete state. Commit fixups in dependency order.

## Summary Shape

Compact success:

```markdown
## Fix-CI Complete
<failure> -> <fix> | Verification: STRONG | Review: <status>
Next: <specific next action>
```

Full/partial:

```markdown
## Fix-CI Complete
<what failed and what was fixed>

### Review
- Rounds: <N> | Pre-flight: <pass/fail/skipped> | Status: <status>

### What to do next
- <specific next action>

### Open risks
- <anything uncertain or untested>
```
