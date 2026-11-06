# Cherry-Pick Gotchas

Failure modes from past runs. Add an entry when a new one surfaces.

## 1. Code from adjacent commits leaks into a pick

Build and tests pass, and an unrelated change from a neighbouring source
commit ships with it, with or without conflicts. A conflict resolved toward the
source side takes whatever neighbouring commits changed in that region; and
code the commit moves or copies is the source branch's version, so a
neighbour's earlier change to it rides along even on a clean apply.
`scripts/scope-audit.sh` on every pick names the source-side commit behind each
extra line and the lines a move carried in. Revert any line that doesn't trace
to the picked commit.

## 2. CHERRY_PICK_HEAD missing after modify/delete-only conflicts

`git cherry-pick --continue` says "no cherry-pick or revert in progress" after
resolving modify/delete conflicts with `git rm`: some git versions drop
`CHERRY_PICK_HEAD` when every remaining conflict is modify/delete, and it also
vanishes after an abort not followed by a fresh pick. Check
`.git/CHERRY_PICK_HEAD` before `--continue`; if a re-run reproduces it, use the
`git commit -C` step in [references/apply.md](references/apply.md), not
`git apply`.

## 3. Bug fix dropped for missing architecture, bug forgotten

A pick is rejected or trimmed because the target lacks architecture; the user
hears "Rejected", and the bug, still live on the target through another path,
is never raised. When a bug-fix pick is rejected or trimmed, check whether the
bug exists on the target another way; if so it goes in the report's "What to
do next".

## 4. Conflict resolution adds indentation and trips line-length lint

Tests pass locally, then pre-commit or CI fails with `E501 Line too long` on
lines that were fine on the source: the target nests the code one level
deeper. Run pre-commit on the changed files before the push and amend fixes
into the in-progress cherry. Never push first and force-push later.

## 5. Push batched at the end

Every cherry was committed locally and pushed once at the end, so CI couldn't
attribute a failure without bisecting. Push each cherry right after it
validates.

## 6. `git apply` prescribed for a partial pick

A partial pick landed with the local user as author and a hand-written message
without the `-x` trailer, noticed after the push. `git format-patch -1 <sha> --
<subset> | git apply --3way` looks clean because it avoids modify/delete
conflicts, but it drops the source author and forces a manual commit; a worker
told to use it skips the ladder. Use `git cherry-pick -x <sha>` even for
partials: `git rm` the inapplicable files and `--continue`. Excluded files show
only in the diff, never in the message or author.

If it was already pushed: reset to before the bad commit, re-pick with `-x`,
re-pick the later commits, then `git push --force-with-lease`, which needs the
user's explicit approval. Amending only the message leaves the wrong author.

## 7. Blocked row with no path to unstick

A `Blocked` or `Rejected` row that stops at "file X doesn't exist on target"
leaves the user to find the prerequisites. Run
[references/unblock-discovery.md](references/unblock-discovery.md) unless the
rejection is intrinsic.
