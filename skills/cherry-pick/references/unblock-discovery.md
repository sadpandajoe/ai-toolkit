# Unblock Discovery

When a row ends `Blocked` or `Rejected` because the target lacks something
(modify/delete files, a prerequisite, missing architecture, divergence past
adapting), name the upstream PRs that, picked first, would unstick it, with
their true cost. Inform only: never queue them yourself.

Skip when the rejection is intrinsic (behavior-changing API rewrite, dependency
bump, build-system change) and record "no unblock path".

## Find and measure

1. For each missing file, module or API: `git log <source-branch> --oneline --
   <path>` and `gh pr list --search "<file-or-symbol>" --state merged --limit
   10`. For each flagged prerequisite commit: `gh pr list --search <sha>`.
2. Keep candidates merged on the source and absent from the target (`git log
   <target> --grep "cherry picked from commit <sha>"` is empty). Never drop a
   large required prerequisite: that produces a false "no path" or a
   deceptively short chain.
3. Measure all survivors in one call; never estimate from the title:

   ```bash
   <skill-dir>/scripts/unblock-measure.sh <owner/repo> <pr>...
   ```

   Per PR: files, lines added and removed, the `migrations/versions/` flag and
   an `easy | heavy | risky` rating, then a `chain` row with totals and the
   worst rating. A migration means risky.

## Result

Order the candidates (apply first to last), say what each unblocks, and keep
the script's numbers. A rating may be raised (shared infrastructure, auth,
RLS), never lowered.

```markdown
## Unblock Discovery — <pr-or-sha>
Blocker: <one-line reason>
Unblock path: yes | no | unclear
Difficulty: easy | heavy | risky — <total files across the chain; any migration>

### Candidates (apply first → last)
1. #<pr> `<source-sha>` — <title>. <N files, +A/-D, migration: yes/no>. Difficulty: <rating>. Unblocks: <file/symbol/prereq>.

### Notes
<one paragraph max; a large feature PR or a migration in any link is said outright>
```

A `yes` path that is `risky` is not the same offer as an `easy` one; the
difficulty is the headline. It goes into the row's notes and the report's next
steps; if the user accepts, re-run the batch with the candidates ahead of the
blocked row.
