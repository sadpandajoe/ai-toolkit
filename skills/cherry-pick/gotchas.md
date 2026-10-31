# Cherry-Pick Gotchas

Failure modes from past runs, as **Symptom** → **Why** → **Do instead**. Add an
entry when a new one surfaces.

## 1. Code from adjacent commits leaks into a pick

**Symptom:** build and tests pass, and an unrelated change from a neighbouring
source commit ships with it, with or without conflicts.

**Why:** a cherry-pick applies only the source commit's diff, so leaks arrive
two ways. A conflict resolved toward the source side takes whatever
neighbouring commits changed in that region. And code the commit moves or
copies is the source branch's version, so a neighbour's earlier change to it
rides along even on a clean apply with no markers.

**Do instead:** run `scripts/scope-audit.sh` on every pick, clean applies
included. It names the source-side commit behind each extra line and, for each
file the commit adds, the lines a move carried from a neighbour. Revert any
line that doesn't trace to the picked commit.

## 2. CHERRY_PICK_HEAD missing after modify/delete-only conflicts

**Symptom:** `git cherry-pick --continue` says "no cherry-pick or revert in
progress" after resolving modify/delete conflicts with `git rm`.

**Why:** some git versions drop `CHERRY_PICK_HEAD` when every remaining
conflict is modify/delete; it also vanishes after an abort not followed by a
fresh pick.

**Do instead:** check `.git/CHERRY_PICK_HEAD` before `--continue`. If a re-run
reproduces it, use the manual-commit step of the ladder in
[references/apply.md](references/apply.md), not `git apply`.

## 3. Bug fix dropped for missing architecture, bug forgotten

**Symptom:** a pick is rejected or heavily trimmed because the target lacks
architecture; the user hears "Rejected", and the bug, still live on the target
through another code path, is never raised.

**Why:** adaptation notes bury the residual risk, and "Rejected" sounds final.

**Do instead:** when a bug-fix pick is rejected or trimmed, check whether the
bug exists on the target another way; if so, it goes in the report's "What to
do next" as an action.

## 4. Conflict resolution adds indentation and trips line-length lint

**Symptom:** tests pass locally, then pre-commit or CI fails with `E501 Line
too long` on lines that were fine on the source.

**Why:** the target nests the code one level deeper; `git cherry-pick` doesn't
reformat, and tests say nothing about lint.

**Do instead:** pre-commit on the changed files before push, amending fixes
into the in-progress cherry. Never push first and force-push later.

## 5. Push batched at the end

**Symptom:** every cherry is committed locally and pushed once at the end, so
CI can't attribute a failure without bisecting.

**Why:** "apply, validate, next, …, push" is the natural loop rhythm.

**Do instead:** push each cherry right after it validates; batch only when the
user asks.

## 6. `git apply` prescribed for a partial pick

**Symptom:** a partial pick lands with the local user as author and a
hand-written message that breaks the `cherry-pick -x` convention, noticed after
the push.

**Why:** `git format-patch -1 <sha> -- <subset> | git apply --3way` looks clean
because it avoids modify/delete conflicts, but `git apply` drops the source
author and forces a manual commit. A worker follows the prompt and skips the
ladder.

**Do instead:** `git cherry-pick -x <sha>` even for partials; `git rm` the
inapplicable files and `--continue` keeps the author and the `(cherry picked
from commit ...)` trailer. When a manual commit is unavoidable, `git commit -C
<sha>`, then amend in the trailer. Excluded files show only in the diff, never
in the message or author.

**If already pushed:** reset to before the bad commit, re-pick with `-x`,
re-pick later commits onto the corrected base, then `git push
--force-with-lease`, which needs the user's explicit approval (the run covers
fast-forward pushes only). Amending only the message leaves the wrong author.

## 7. Blocked row with no path to unstick

A `Blocked` or `Rejected` row that stops at "file X doesn't exist on target"
leaves the user to find the prerequisites. Run
[references/unblock-discovery.md](references/unblock-discovery.md) unless the
rejection is intrinsic.
