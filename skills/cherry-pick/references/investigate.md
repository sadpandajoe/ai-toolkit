# Cherry-Pick Investigation

Produces the raw analysis the gate and the plan consume. Investigation reports
what it **observed**; the go/no-go call is the gate's.

## Tracks

1. **Source analysis:** resolve the PR to its commit(s), classify the change
   (functional, structural, dependency, mixed), and list the distinct sub-fixes
   of a bundled PR, noting which are entangled and must move together.
2. **Target compatibility:** list modify/delete files explicitly (source files
   missing on the target); downstream phases need the list. Flag any change to
   `package.json`, lockfiles or other dependency manifests as a dependency
   change.
3. **Prerequisites:** earlier commits the change depends on, and whether an
   equivalent fix is already on the target, via the debug skill's
   [check-existing-fix reference](../../debug/references/check-existing-fix.md)
   (see its skip rules for dependency upgrades and mixed PRs).
4. **Target-affected scan** (does the bug even manifest on target?)

   Distinct from tracks 2 and 3: target-compat asks "do the files exist," existing-fix asks "is the fix already here." This asks **"is the bug even live on target?"** A fix that applies cleanly to UNFIXED, files-present code is still a no-op — or a harmful change — if the buggy condition was never on the target branch (classic: a regression introduced by a commit that only shipped to master). This is a backport-only concern; keep it here, not in the shared `check-existing-fix` helper (on same-branch fixes the bug is trivially present).

   Run **cheap → deep** and stop at the first conclusive signal:
   - **Cheap (the common case):** does the buggy pre-fix code exist on target? Grep the target branch for the lines the patch *changes or removes* (the `-` / context side of the hunks). Present → **AFFECTED**, stop — this is the normal pre-existing-bug case and needs no deeper trace.
   - **Deep (only when the buggy code is absent):** is this a regression fix? Identify the commit that introduced the bug (from the PR/issue body, or `git log -S'<buggy snippet>'` / `git blame` on the changed lines), then `git merge-base --is-ancestor <introducing-sha> <target-branch>`. Not an ancestor, and no PR-number/`-x` match on target → the regression never reached target → **NOT_AFFECTED**.

   **Verdict rules** — the errors are asymmetric, so the NOT_AFFECTED bar is deliberately high. A false NOT_AFFECTED silently drops a real fix and nobody notices; a false AFFECTED is caught downstream (empty cherry / conflict / scope audit).
   - **NOT_AFFECTED** only on concrete not-present evidence: a *named* introducing commit demonstrably not on target, or the buggy code path demonstrably absent.
   - **UNCLEAR** whenever you can't find the origin or the signal is ambiguous — never skip on absence of evidence.
   - **Keep this orthogonal to "can't apply."** A bug that *is* live on target but whose fix won't apply is **AFFECTED** (and becomes Blocked/Partial in apply) — not NOT_AFFECTED. Manifestation and applicability are different axes.

## Output

Fill in [../assets/investigation-template.md](../assets/investigation-template.md):

- The **Raw Signals for Gate** block is required; the gate classifies from it.
- Prefer a summary line ("12 files apply cleanly, 2 need adaptation, 1 doesn't
  exist on target") over a table of repeated "OK" rows.
- Omit sections that don't apply; write "N/A" once rather than filling a table
  with "none".
