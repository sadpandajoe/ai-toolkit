# Unblock Discovery

When a cherry-pick terminates as `Blocked` or `Rejected`, the orchestrator must not let it die in the report with "skipped because X." Run an unblock-discovery subagent to identify the **specific upstream PRs/commits that, if cherry-picked first, would unstick this change**, and surface them in the final report.

Mode is **inform-only** by default. The subagent does not investigate, gate, plan, or apply the candidate dependencies — it only names them. Auto-picking is a future extension.

For release-candidate Shortcut stories, the unblock path found here feeds the owner-notification comment (its "how to unblock it" element) — see [blocked-owner-comment.md](blocked-owner-comment.md). Discovery finds *what would unstick it*; that reference *tells the labeler and asks them to decide*.

## When to Run

Run for every row whose terminal `Result` is `Blocked` or `Rejected`, including:
- Modify/delete because target lacks files the source touched
- Prerequisite commits flagged during investigate but not present on target
- Reject-category change where the rejection is "architecture missing on target" rather than "wrong shape of change" (e.g., feature depends on a refactor that hasn't shipped)
- Conflict resolution escalated past adapt because target diverged structurally

**Skip** when the rejection is intrinsic — e.g., behavior-changing API rewrite that should never be cherry-picked at all, dependency-bump PR, build-system change. There's no "add prerequisite X" that makes a reject-category cherry safe; record "no unblock path" and move on.

## Subagent Contract

The subagent runs in an isolated context. Tier: **Standard** by default; **Heavy** if investigation produced a long prerequisite list or the blocker spans multiple modules.

### Inputs

Provide the worker with:
- Source SHA and PR
- Target branch
- Investigation output (especially "Raw Signals for Gate" — modify/delete files, prerequisite commits, target-side missing modules)
- Result label and blocker reason (one line)
- The execution-table row's `Notes`

Do NOT pass full diffs or raw logs — the subagent works from the structured signals.

### Steps

1. For each missing file/module/API the investigation flagged on the target:
   - `git log --all --source --oneline -- <path>` on the source branch (or repo-wide) to identify the commit(s) that introduced or last touched it relevantly.
   - `gh pr list --search "<file-or-symbol>" --state merged --limit 10` and `gh search prs "<symbol>" --merged` to surface candidate PRs.
2. For each prerequisite commit flagged during investigate, resolve the owning PR via `gh pr list --search <sha>` or `git log --grep <sha>`.
3. Filter on provenance only: keep candidates that are (a) merged into the source branch and (b) not already on the target branch (`git log <target> --grep "cherry picked from commit <sha>"` returns nothing). Do **not** drop a candidate for being large — if the blocked change genuinely needs it, the chain is heavy and the report must say so. Silently dropping a required heavy prereq produces a false "no path" or a deceptively short chain.
4. **Measure each surviving candidate — do not estimate from the title.** Run `gh pr view <pr> --repo <repo> --json title,changedFiles,additions,deletions,files` and record:
   - `changedFiles` and `+additions/-deletions`.
   - **Migration**: yes if any file matches `migrations/versions/`. A schema migration on a stable release branch is a major escalation, never "just another cherry."
5. **Rate each candidate's cherry difficulty from the measured facts** (this is the line that stops a chain from reading as "two quick cherries"):
   - **easy** — small (≲15 files), no migration, self-contained.
   - **heavy** — large feature PR (≳30 files) or a wide refactor; large conflict/review surface even if mechanically clean.
   - **risky** — carries a DB migration, or touches shared infra/auth/RLS. Always overrides `heavy`/`easy`.
6. For each candidate, write one line carrying the numbers, the migration flag, the rating, and what it unblocks.

### Output

Return exactly this block. No diffs, no logs.

```markdown
## Unblock Discovery — <pr-or-sha>
Blocker: <one-line reason>
Unblock path: yes | no | unclear
Difficulty: easy | heavy | risky — <one line: total files across the chain, and whether any link carries a migration>

### Candidates (order matters: apply first → last)
1. #<pr> `<source-sha>` — <title>. <N files, +A/-D, migration: yes/no>. Difficulty: easy|heavy|risky. Unblocks: <which file/symbol/prereq this introduces>.
2. #<pr> `<source-sha>` — <title>. <…>. Difficulty: …. Unblocks: <…>.

### Notes
<one paragraph max — caveats, ordering risks. State the cost in plain terms: if any link is a large feature PR or carries a migration, say so explicitly — that is the difference between "two quick cherries and we're in" and "a release-branch schema change plus a 90-file feature." Never let a heavy/risky chain read as easy.>
```

`Difficulty` is mandatory and is the honest headline: a `yes` path that is `risky` is not the same offer as a `yes` path that is `easy`, and the report must not blur them.

If `Unblock path: no`, state why in one line (e.g., "blocker is API rewrite touching 40+ files; no single prerequisite would unstick it").

If `Unblock path: unclear`, list whatever partial signal exists and flag that a deeper investigation is needed.

## Orchestrator Responsibilities

- Insert the discovery block into `CHERRY_PICK.md` under the row's Subagent Handoff entry (field `Unblock candidates`).
- Carry the candidate list **with its difficulty** into the Final Report under **What to do next** as: "Could cherry `<pr-or-sha>` if we first apply: #X, #Y, #Z — `<difficulty>`: <e.g. #X is 89 files + a DB migration>." Never present the chain as a bare PR list; the cost is part of the offer.
- Do **not** automatically queue the candidates for cherry-pick. The user decides whether to add them to the run.
- If the user accepts the candidates, re-enter the batch flow with the new PRs prepended to the wave that contains the blocked row.

## Future Extension (Auto-Unblock)

When `--auto-unblock` is added: the orchestrator may, with user pre-authorization, prepend the candidate list to the active wave and re-run from sequence planning. Until then, this skill stays inform-only — the surface area for "we cherry-picked the wrong dependency and made things worse" is too large to fire silently.
