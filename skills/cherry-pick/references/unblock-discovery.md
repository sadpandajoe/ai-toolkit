# Unblock Discovery

When a cherry-pick ends `Blocked` or `Rejected`, do not let it die in the
report as "skipped because X". Name the **specific upstream PRs that, picked
first, would unstick it**, with their true cost. Mode is **inform-only**: the
candidates are not investigated, gated, planned or applied here.

For release-candidate stories, the path found here is the "how to unblock it"
element of the owner comment ([blocked-owner-comment.md](blocked-owner-comment.md)).

## When to Run

Every row whose terminal `Result` is `Blocked` or `Rejected`, including:
- modify/delete because the target lacks files the source touched;
- prerequisite commits flagged during investigate but absent on the target;
- a rejection for "architecture missing on target" rather than "wrong shape of
  change";
- conflict resolution escalated past adapt because the target diverged.

**Skip** when the rejection is intrinsic (behavior-changing API rewrite,
dependency bump, build-system change): no prerequisite makes it safe. Record
"no unblock path" and move on.

## Parent: Find and Measure

1. For each missing file, module or API from the investigation: `git log
   --all --source --oneline -- <path>`, `gh pr list --search
   "<file-or-symbol>" --state merged --limit 10`.
2. For each flagged prerequisite commit, resolve its PR (`gh pr list --search
   <sha>`).
3. Keep candidates merged into the source branch and not on the target (`git
   log <target> --grep "cherry picked from commit <sha>"` is empty). Do **not**
   drop a large required prerequisite: silently dropping one produces a false
   "no path" or a deceptively short chain.
4. Measure every surviving candidate in one call; do not estimate from the
   title:

   ```bash
   <skill-dir>/scripts/unblock-measure.sh <owner/repo> <pr>...
   ```

   Per PR it prints files, lines added and removed, the `migrations/versions/`
   flag and an `easy | heavy | risky` rating, then a `chain` row with the
   totals and the worst rating. A migration means risky.

The review worker receives only that output, the blocker reason, and the
investigation's raw signals (modify/delete files, prerequisites, missing
modules); no diffs or logs.

## Worker: Synthesize

Order the candidates (apply first → last), say what each one unblocks, and
keep the script's numbers and ratings. A rating may be raised (shared
infrastructure, auth, RLS), never lowered. Return exactly:

```markdown
## Unblock Discovery — <pr-or-sha>
Blocker: <one-line reason>
Unblock path: yes | no | unclear
Difficulty: easy | heavy | risky — <total files across the chain, and whether any link carries a migration>

### Candidates (order matters: apply first → last)
1. #<pr> `<source-sha>` — <title>. <N files, +A/-D, migration: yes/no>. Difficulty: easy|heavy|risky. Unblocks: <file/symbol/prereq>.

### Notes
<one paragraph max: caveats and ordering risks, with the cost in plain terms. A large feature PR or a migration in any link must be said outright.>
```

`Difficulty` is the honest headline: a `yes` path that is `risky` is not the
same offer as an `easy` one. For `no`, give the reason in one line; for
`unclear`, list the partial signal and flag that deeper investigation is
needed.

## After Discovery

The block goes in the row's `Unblock candidates` handoff field in
`CHERRY_PICK.md`, and into the final report's "What to do next" with its
difficulty ([final-report.md](../examples/final-report.md)). Never queue the
candidates automatically; if the user accepts them, re-enter the batch flow
with them ahead of the blocked row ([SKILL.md](../SKILL.md)).
