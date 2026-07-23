# Code Review Principles

## Core Principles
- **DRY** — Check three forms of duplication before accepting new code:
  1. **Within the repo** — similar logic already exists? Extract if maintained together, parameterize if independent.
  2. **Against installed packages** — does a dependency in `package.json` / `requirements.txt` / `go.mod` / equivalent already provide this? Reimplementing utilities from a shipped library or internal shared package is `[minor]` — or `[major]` if the reimplementation drifts from documented behavior the library has already gotten right.
  3. **Against language built-ins** — modern stdlib often covers what looks custom (`Object.groupBy`, `Array.prototype.flatMap`, `itertools.groupby`, etc.). Flag custom helpers that duplicate built-ins.
- **Consistency** — follow existing patterns and conventions (grep for similar files to find them)
- **Modeling** — logic lives in the right module/package/class; signatures match neighbors; new code is placed where a future reader would look for it
- **File-size smell** — a diff that pushes a file across 1000 lines (from under 1000 to over, or already over 1000 and grown materially by the diff) is a `[minor]` decomposition prompt by default; ask whether it should be split first. Escalate to `[major]` under the deep-quality lens (`skills/review/references/deep-quality.md`).
- **Spaghetti growth** — new ad-hoc conditionals or one-off branches inserted into unrelated flows are a design problem, not a style nit; prefer a helper/model/module over tangling an existing path. `[minor]` when it worsens legibility, `[major]` when it makes an existing flow materially harder to reason about.
- **Test quality** — tests should not silently pass (always-green tests are noise); data should match types

## Scoring

Use the universal rubric in `rules/scoring.md`. Score each component:

| Component | What to evaluate |
|-----------|-----------------|
| **Root Cause** | Is the underlying problem identified? |
| **Solution** | Is the fix clean, maintainable, and minimal? |
| **Tests** | Do tests cover the changed behavior meaningfully? |
| **Code** | Is the code readable, consistent, and correct? |
| **Docs** | Are changes self-explanatory or properly documented? |

A single blocking component (1-2) pulls the overall score into the 3-5 range — the overall is not a simple average.

## Severity Tags

Use the canonical code-review tags and definitions from `rules/severity.md`.
This rule only adds the test-coverage calibration below.

### Test Coverage Severity Calibration

Missing tests are not always the same severity. Calibrate based on what the change actually does:

| Change Type | Missing Tests | Severity | Rationale |
|-------------|--------------|----------|-----------|
| New public function/method with logic | No tests | **[major]** | Untested logic is a regression waiting to happen |
| New API endpoint or route | No integration test | **[major]** | Contract changes need verification |
| Bug fix | No regression test | **[major]** | The same bug will come back |
| Behavioral change to existing code | No updated tests | **[major]** | Tests should prove the new behavior works |
| Config change, feature flag, env var | No test | **[minor]** | Lower risk, but still worth testing |
| Doc-only, comment-only, type annotation | No test | Not a finding | No behavior changed — tests would be noise |
| Rename, move, reformatting | No test | Not a finding | Mechanical change — compiler/linter covers this |
| One-liner typo fix in non-logic code | No test | Not a finding | Test would be testing a string literal |

**Impact escalation**: When the impact assessment (from the `qa` skill's `references/assess-impact.md`) is CORE, shift all "missing test" findings up one severity level. A config change with no test is normally `[minor]` — but if it touches a CORE workflow (login, auth, payment), it becomes `[major]`.

When reviewing, **assess what the PR does before scoring test coverage**. A blanket "no tests = major" penalizes trivial PRs unfairly and lets risky PRs hide behind a few token tests.

## Invalid Review Patterns
- Minor formatting (periods, spacing)
- Personal style preferences
- Demanding specific implementation
- Scope creep (unrelated fixes)

## Finding Calibration

Rules of thumb for grading and triaging findings. They apply to every review path — single-reviewer, adversarial, and multi-reviewer synthesis.

- **Scope is upstream of correctness.** Before grading whether a finding is a real bug, confirm its `file:line` is actually in the diff. If the cited code is unchanged by the change set, drop the finding regardless of whether it's correct — it's a pre-existing-code observation, not a review of this change. Adjudicate correctness only for in-scope findings.
- **Symmetry findings cap at `[minor]`.** "The same problem exists in sibling path X" is at most `[minor]`, and only if the change's stated scope plausibly covers X *or* the change worsened X. If X is unchanged and not worsened, it's a follow-up-PR suggestion masquerading as a finding — note it in the summary's Remaining section, don't grade it. Symmetry findings feel rigorous ("I traced all N call sites") but reward breadth over the risk the change actually introduced.
- **Convergent beats single-source.** When two independent reviewers (different model, fresh context) surface the same finding without prompting, treat it as high-confidence and keep its severity. A finding only one reviewer raised is worth investigating but rarely worth blocking on alone — verify before promoting it past `[minor]`.
- **History audit before grading a "wrong semantics" finding.** When a change reverses or amends prior behavior, scan recent history of the touched files (`git log --follow -p <file> | head -200`) for the PR it's undoing. A change that looks like a regression is often a conscious reversal the history already justifies.
- **Don't leading-question subagents.** When spawning reviewer subagents, the prompt supplies diff facts, lens list, and posture — never a finding shape ("look for a case where X breaks", "check if Y is null"). Steering a worker toward a specific finding pre-decides what matters and reproduces the orchestrator's framing as findings. The lens already encodes what to look for.
