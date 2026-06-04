# Unblock Discovery

When a cherry-pick terminates as `Blocked` or `Rejected`, the orchestrator must not let it die in the report with "skipped because X." Run an unblock-discovery subagent to identify the **specific upstream PRs/commits that, if cherry-picked first, would unstick this change**, and surface them in the final report.

Mode is **inform-only** by default. The subagent does not investigate, gate, plan, or apply the candidate dependencies — it only names them. Auto-picking is a future extension.

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
3. Filter candidates: keep only those that are (a) merged into the source branch, (b) not already on the target branch (`git log <target> --grep "cherry picked from commit <sha>"` returns nothing), and (c) plausibly self-contained enough to cherry-pick (use commit message + file count as a cheap heuristic).
4. For each surviving candidate, write one line: `#<pr> "<title>" — unblocks <reason>`.

### Output

Return exactly this block. No diffs, no logs.

```markdown
## Unblock Discovery — <pr-or-sha>
Blocker: <one-line reason>
Unblock path: yes | no | unclear

### Candidates (order matters: apply first → last)
1. #<pr> `<source-sha>` — <title>. Unblocks: <which file/symbol/prereq this introduces>.
2. #<pr> `<source-sha>` — <title>. Unblocks: <…>.

### Notes
<one paragraph max — caveats, ordering risks, "candidate #2 is itself a feature change and may not be safe to cherry">
```

If `Unblock path: no`, state why in one line (e.g., "blocker is API rewrite touching 40+ files; no single prerequisite would unstick it").

If `Unblock path: unclear`, list whatever partial signal exists and flag that a deeper investigation is needed.

## Orchestrator Responsibilities

- Insert the discovery block into `CHERRY_PICK.md` under the row's Subagent Handoff entry (field `Unblock candidates`).
- Carry the candidate list into the Final Report under **What to do next** as: "Could cherry `<pr-or-sha>` if we first apply: #X, #Y, #Z."
- Do **not** automatically queue the candidates for cherry-pick. The user decides whether to add them to the run.
- If the user accepts the candidates, re-enter the batch flow with the new PRs prepended to the wave that contains the blocked row.

## Future Extension (Auto-Unblock)

When `--auto-unblock` is added: the orchestrator may, with user pre-authorization, prepend the candidate list to the active wave and re-run from sequence planning. Until then, this skill stays inform-only — the surface area for "we cherry-picked the wrong dependency and made things worse" is too large to fire silently.
