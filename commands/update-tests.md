# /update-tests - Improve an Existing Test Suite


> **When**: You want to improve an existing test suite in a specific area, path, or function and have the workflow analyze gaps, update tests, verify, and review.
> **Produces**: Scoped test updates, verification results, remaining follow-up gaps, and either an authorized `test:` commit or a clear handoff.

## Usage
```
/update-tests sql-lab
/update-tests src/features/sql-lab
/update-tests tests/unit/sql_lab/
/update-tests --function normalize_query
```

## Command Contract

- Only the main thread writes PROJECT.md. Subagents return compact handoffs.
- For STANDARD or expensive runs (large suite, multi-subsystem target, repeated `/review-code` rounds), follow `rules/context-management.md`: write durable state to PROJECT.md at each phase boundary, then `/checkpoint --clear` before the next expensive phase. The internal `/review-code` loop counts as one of those phases.
- Required PROJECT.md updates on STANDARD/expensive runs:
  - After step 3 (gap analysis): `## Test Suite Analysis` (target, weak tests, missing coverage, planned updates).
  - After step 6 (updates applied): `## Test Updates Applied` (files changed, tests added/updated, replaced low-signal tests).
  - After step 7 (verify + review): `## Test Review Status` (verification strength, review rounds, Review Gate status).
- These writes are **hard gates before any `/checkpoint --clear`** on STANDARD/expensive runs — clearing without them loses the gap analysis or fix queue.
- For STANDARD work, emit the Phase Plan block from `rules/complexity-gate.md` after classification.

## Steps

1. **Normalize the Target**

   Accept:
   - a product area such as `sql-lab`
   - a repo path
   - a test file or test directory
   - `--function <name>`

   Resolve the target by searching matching product-area names, code paths, and test paths.
   If multiple plausible targets remain, stop and surface the ambiguity.

2. **Discover the Existing Suite**

   Identify the meaningful existing tests for the target area before planning any updates.

   If no meaningful suite exists:
   - stop and recommend `/create-tests`
   - do not create the first suite inside `/update-tests`

3. **Analyze the Current Suite**

   Load [skills/testing/references/review-tests.md](../skills/testing/references/review-tests.md) to identify:
   - weak or low-signal tests
   - missing behavioral coverage
   - production blind spots
   - simplification opportunities

4. **Expand Use Cases When Needed**

   For workflow-heavy, integration-heavy, or user-visible targets:
   - run QA use-case analysis to produce a compact must-cover scenario matrix

5. **Scope the Smallest Useful Update**

   Collapse the findings into:
   - must-update now
   - suggested follow-up tests
   - out-of-scope risks

   Keep the current change focused on the smallest set of high-signal suite improvements.

6. **Update the Tests**

   Load [skills/testing/references/update-tests.md](../skills/testing/references/update-tests.md):

   This helper owns:
   - updating existing tests first
   - adding tests only where they fit the current suite naturally
   - replacing low-signal tests when the replacement is clearly better
   - writing failing tests first when feasible
   - targeted verification

7. **Verify and Review Changed Test Files**

   Run `/verify` or equivalent targeted checks first, then run `/review-code` on the changed repo-tracked files as an internal loop.
   Keep iterating until only nitpicks remain or a real blocker/user decision appears.

8. **Commit Boundary**

   If the user explicitly requested commit behavior, verification is strong, and `/review-code` leaves no unresolved `[major]` or `[minor]` issues:
   - create a `test:` commit

   Commit message format:
   - `test: update <scope> coverage`
   - fallback: `test: update targeted coverage`

   Stop instead of committing when:
   - commit behavior was not explicitly requested
   - verification is partial or blocked
   - meaningful ambiguity remains
   - the workflow handed off to `/create-tests`

9. **Summary**
   ```markdown
   ## Update-Tests Complete

   ### Outcome
   - [Updated suite / handed off to create-tests / stopped on blocker]

   ### Scope
   - [Target area, path, or function]

   ### Suite Outcome
   - [Updated existing suite / handed off to create-tests]

   ### Behavioral Coverage
   - [What regressions or behaviors are now covered]

   ### Review / Quality
   - [Review rounds and final review outcome]

   ### Verification
   - [Checks run]

   ### Risks / Blockers
   - [Anything still weak, blocked, or intentionally left for follow-up]

   ### Remaining Gaps
   - [Suggested follow-up tests or none]

   ### Commit Result
   - [Created `test:` commit / no commit and why]
   ```

## Notes
- `/update-tests` is the public workflow for existing-suite maintenance
- Favor replacing low-signal tests over adding redundant ones
- Write the failing test first when feasible; if blocked, document why before changing the suite
- `/review-code` is an internal phase here, not the expected next top-level user step
- Every run writes at least a one-line `## Tests Updated` entry to PROJECT.md before the chat summary so `/clear` or `/archive-project-file` after `/update-tests` does not lose the record. TRIVIAL/MODERATE runs satisfy this with a single end-of-run entry; STANDARD/expensive runs follow the hard-gate cadence in the Command Contract.

  Minimum entry shape for TRIVIAL/MODERATE:

  ```markdown
  ## Tests Updated
  Files: [list]
  Change: [one-liner — what behavior changed or got covered]
  Verification: [strength label]
  Commit: [SHA or "no commit"]
  ```

  Emit before the chat summary:

  ```markdown
  ## PROJECT.md Updated — Tests Updated
  Files recorded: [count]
  ```
