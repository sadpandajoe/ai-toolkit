# Create the First Meaningful Tests


> **When**: You want standalone test-only work for an area that does not yet have a meaningful suite, or `update-tests` has handed off because there is nothing real to update.
> **Produces**: A first meaningful test suite or net-new high-signal coverage, validation results, and a summary of remaining gaps.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `create-tests` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage
```
create-tests                         # First meaningful tests for current uncommitted work
create-tests <file>                  # First meaningful tests for a specific file
create-tests --function <name>       # First meaningful tests for a specific function
```

## Command Contract

- Only the main thread writes PROJECT.md. Subagents return compact handoffs.
- For STANDARD or expensive runs (large untested surface, multi-subsystem scope), follow `rules/context-management.md`: write durable state to PROJECT.md at each phase boundary, then hand the next expensive phase to a fresh worker.
- Required PROJECT.md updates on STANDARD/expensive runs:
  - After step 2 (initial tests written): `## Tests Created` (files added, behaviors covered, test layer chosen).
  - After step 3 (verify + review): `## Test Review Status` (verification result, review gate status).
- These writes are **hard gates before any checkpoint** on STANDARD/expensive runs.

## Steps

1. **Determine Scope**

   Identify the code to test:
   - Uncommitted changes: `git diff --name-only`
   - Specific file or function: as provided
   - Read the code thoroughly before writing any tests

2. **Create Initial Tests**

   Load [skills/testing/references/create-tests.md](../../testing/references/create-tests.md) for this step. This testing context owns:
   - running `review-tests` before writing tests
   - choosing the right test layer
   - creating the first meaningful tests for the target area
   - targeted verification

3. **Review Changed Test Files**

   Run `verify` or equivalent targeted checks first, then run `review-code` on the changed repo-tracked files: one independent review, fix the accepted findings, one delta pass over the fix. A finding still open after the delta is `ESCALATE` (or `USER_DECISION` when it needs a product call), not a third round.

4. **Summary**
   ```markdown
## Create-Tests Complete

   ### Outcome
   - [Created first meaningful suite / stopped on blocker]

   ### Scope
   - [What behavior or files were covered]

   ### Behavioral Coverage
   - [What regressions or behaviors are now covered]

   ### Review / Quality
   - [Review rounds and final review outcome]

   ### Verification
   - [Checks run]

   ### Risks / Blockers
   - [Anything still unverified or out of scope]

   ### Remaining Gaps
   - [Anything still not covered]

   ### Next Decision
   - [Ready for manual commit / needs more work]
   ```

## Notes
- `create-tests` is a test-only command, not the normal entrypoint for feature or bug workflows
- Favor the smallest set of high-signal tests over broad test quantity
- `review-code` is an internal phase here, not the expected next top-level user step
- Stop before committing unless the user explicitly requested commit/push behavior.
- Every run writes at least a one-line `## Tests Created` entry to PROJECT.md before the chat summary so a fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md) after `create-tests` does not lose the record. TRIVIAL/STANDARD runs satisfy this with a single end-of-run entry; COMPLEX or expensive runs follow the hard-gate cadence in the Command Contract.

  Minimum entry shape for TRIVIAL/STANDARD:

  ```markdown
  ## Tests Created
  Files: [list]
  Behaviors covered: [one-liner]
  Verification: [strength label]
  ```

  Emit before the chat summary:

  ```markdown
  ## PROJECT.md Updated — Tests Created
  Files recorded: [count]
  ```
