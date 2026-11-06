# Unblock Discovery

When a row ends `Blocked` or `Rejected` because the target lacks something,
name the upstream PRs that, picked first, would unstick it, with their true
cost. Inform only: never queue them yourself. When the rejection is intrinsic
(a behavior-changing API rewrite, a dependency bump, a build-system change),
record "no unblock path" instead.

Keep candidates merged on the source and absent from the target. Never drop a
large required prerequisite: that produces a false "no path" or a deceptively
short chain. Measure every survivor in one call, never from the title:

```bash
<skill-dir>/scripts/unblock-measure.sh <owner/repo> <pr>...
```

Its header documents the columns and the `easy | heavy | risky` rating (a
migration means risky). Keep its numbers. A rating may be raised (shared
infrastructure, auth, RLS), never lowered.

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

The difficulty is the headline: a `risky` yes is not the same offer as an
`easy` one. It goes into the row's notes and the report's next steps; if the
user accepts, re-run the batch with the candidates ahead of the blocked row.
