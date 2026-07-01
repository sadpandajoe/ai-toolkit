---
tier: Heavy
---

# Cherry-Pick Investigation

Produces the raw analysis that the gate and plan phases consume. This phase does not make the go/no-go decision — that belongs to the gate.

## Goal

Understand the change deeply enough for the gate to decide whether to proceed and for the plan to determine how.

## Parallel Work

Run these tracks in parallel when possible:

1. **Source analysis**
   - Resolve PR URL to commit(s) if needed
   - Inspect commit message, changed files, and nearby history
   - Classify the change as functional, structural, dependency-related, or mixed
   - For bundled PRs: identify and list distinct sub-fixes

2. **Target compatibility scan**
   - Check whether touched files and modules exist on the target branch
   - Compare imports, APIs, and obvious dependency differences
   - Detect deleted or renamed target-side modules
   - **Flag modify/delete risk**: when source files don't exist on target, explicitly list the specific files — downstream phases need this
   - If `package.json`, lockfiles, or equivalent dependency manifests changed, flag as dependency change

3. **Prerequisite scan**
   - Look for earlier commits the change appears to depend on
   - Confirm whether an equivalent fix already exists on the target branch via the `debug` skill's [check-existing-fix reference](../../debug/references/check-existing-fix.md) — see that file's skip rules for dependency upgrades and mixed PRs
   - Identify obvious backport ordering constraints

4. **Target-affected scan** (does the bug even manifest on target?)

   Distinct from tracks 2 and 3: target-compat asks "do the files exist," existing-fix asks "is the fix already here." This asks **"is the bug even live on target?"** A fix that applies cleanly to UNFIXED, files-present code is still a no-op — or a harmful change — if the buggy condition was never on the target branch (classic: a regression introduced by a commit that only shipped to master). This is a backport-only concern; keep it here, not in the shared `check-existing-fix` helper (on same-branch fixes the bug is trivially present).

   Run **cheap → deep** and stop at the first conclusive signal:
   - **Cheap (the common case):** does the buggy pre-fix code exist on target? Grep the target branch for the lines the patch *changes or removes* (the `-` / context side of the hunks). Present → **AFFECTED**, stop — this is the normal pre-existing-bug case and needs no deeper trace.
   - **Deep (only when the buggy code is absent):** is this a regression fix? Identify the commit that introduced the bug (from the PR/issue body, or `git log -S'<buggy snippet>'` / `git blame` on the changed lines), then `git merge-base --is-ancestor <introducing-sha> <target-branch>`. Not an ancestor, and no PR-number/`-x` match on target → the regression never reached target → **NOT_AFFECTED**.

   **Verdict rules** — the errors are asymmetric, so the NOT_AFFECTED bar is deliberately high. A false NOT_AFFECTED silently drops a real fix and nobody notices; a false AFFECTED is caught downstream (empty cherry / conflict / scope audit).
   - **NOT_AFFECTED** only on concrete not-present evidence: a *named* introducing commit demonstrably not on target, or the buggy code path demonstrably absent.
   - **UNCLEAR** whenever you can't find the origin or the signal is ambiguous — never skip on absence of evidence.
   - **Keep this orthogonal to "can't apply."** A bug that *is* live on target but whose fix won't apply is **AFFECTED** (and becomes Blocked/Partial in apply) — not NOT_AFFECTED. Manifestation and applicability are different axes.

## Bundled PRs

When a single PR or commit contains multiple independent fixes:

- Identify and list the distinct sub-fixes during source analysis
- Assess each sub-fix individually against the target branch — some may apply cleanly while others hit architecture mismatches
- If sub-fixes are independent, they can be included or excluded individually
- If sub-fixes are entangled (shared code paths, interdependent changes), note they must be treated atomically

## Batch Execution

When investigating multiple independent changes, prefer parallel subagents (one per change) over sequential investigation in the main context. The within-change tracks (source, target, prereq) are typically fast enough to run sequentially inside a single agent — the bigger parallelism win is across changes.

## Output

Fill in the template at [../assets/investigation-template.md](../assets/investigation-template.md). The "Raw Signals for Gate" block is required — it provides the structured input the gate uses for its difficulty classification.

Keep investigation output compact. A summary line ("12 files apply cleanly, 2 need adaptation, 1 doesn't exist on target") is better than a 12-row table with "OK" repeated.
