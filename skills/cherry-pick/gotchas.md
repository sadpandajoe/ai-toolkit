# Cherry-Pick Gotchas

Failure modes seen in past runs. Read at decision points; add an entry when a
new failure surfaces. Format: **Symptom** → **Why** → **Do instead**.

---

## 1. Code from adjacent commits leaks into a cherry-pick

**Symptom:** the pick builds and tests pass, and an unrelated change from a neighbouring source commit ships with it, with or without conflicts.

**Why:** a cherry-pick applies only the source commit's own diff, so leaked lines arrive one of two ways:
- **A conflict resolved toward the source side.** Where a neighbouring source commit changed the conflicting region, taking the source version of the hunk (or the file) takes the neighbour's change with it.
- **Code the source commit moves or copies.** When the commit moves a function or file, the moved text is the source branch's version, so any change a neighbouring commit made to it before the move rides along, even on a clean apply with no conflict markers.

**Do instead:** run `scripts/scope-audit.sh` on **every** cherry-pick, clean applies included. It compares the exact changed lines of the source commit and the result and names the source-side commit behind each extra line, and its moved-code check lists lines a move carried from a neighbour for each file the source commit adds. Revert any line that does not trace to the cherry-picked commit.

---

## 2. CHERRY_PICK_HEAD missing after modify/delete-only conflicts

**Symptom:** `git cherry-pick --continue` errors with "no cherry-pick or revert in progress" after resolving modify/delete conflicts with `git rm`.

**Why:** some git versions drop `CHERRY_PICK_HEAD` when every remaining conflict is modify/delete; it also disappears after an abort not followed by a fresh pick.

**Do instead:** check `.git/CHERRY_PICK_HEAD` before `--continue`. If a re-run reproduces the state, use the manual-commit step of the [apply.md](references/apply.md) ladder, not `git apply`.

---

## 3. Bug-fix dropped due to architecture mismatch, underlying bug forgotten

**Symptom:** a cherry-pick is rejected or heavily trimmed because the target lacks required architecture. The user is told "Rejected", and the underlying bug, which still affects the target through a different code path, is never surfaced.

**Why:** adaptation notes bury the residual risk, and "Rejected" sounds final.

**Do instead:** when a bug-fix pick is rejected or trimmed, assess whether the bug exists on the target through another path. If yes, put it in the final report's "What to do next" as an actionable item, not in adaptation notes.

---

## 4. Conflict resolution adds indent levels and trips line-length lint

**Symptom:** the pick applies and tests pass locally, but pre-commit or CI fails with `E501 Line too long` on lines that were fine on the source branch.

**Why:** when the target nests the code one level deeper, picked lines arrive with extra indentation and go over the limit; `git cherry-pick` does not reformat, and passing tests say nothing about lint.

**Do instead:** run pre-commit on the changed files during validation, **before push**, and amend the fixes into the in-progress cherry ([validate.md](references/validate.md)). Never push first and force-push later.

---

## 5. Push batched at the end instead of per cherry

**Symptom:** every cherry is committed locally and pushed once at the end, so CI cannot attribute a failure without bisecting.
**Why:** "apply, validate, next, …, done, push" is the natural loop rhythm.
**Do instead:** fill each row's Push cell before any later work (SKILL.md, Per-Cherry Push); batch only when the user asks.

---

## 6. Orchestrator prescribes `git apply` for partial cherry-picks

**Symptom:** a partial cherry-pick lands with the local user as author and a hand-written message that breaks the `cherry-pick -x` convention, found after the push.

**Why:** for a partial pick, `git format-patch -1 <sha> -- <subset> | git apply --3way` looks clean because it avoids modify/delete conflicts, but `git apply` drops the source author and forces a manual commit with a hand-written message. A worker follows the prompt and bypasses the apply.md ladder.

**Do instead:** prescribe `git cherry-pick -x <sha>` even for partials; modify/delete conflicts on inapplicable files resolve with `git rm <files>`, and `git cherry-pick --continue` keeps the author and the `(cherry picked from commit ...)` trailer. When a manual commit is unavoidable, `git commit -C <sha>` preserves author and message; then amend in the `(cherry picked from commit <sha>)` line. Excluded files show only in the diff, never in the message or the author.

**Remediation if already pushed:** reset to before the bad commit, re-run `git cherry-pick -x` properly, re-pick any later commits onto the corrected base, then `git push --force-with-lease` (this needs the user's explicit approval; the run's grant covers fast-forward pushes only). Amending only the message leaves the wrong author.

---

## 7. Blocked cherry reported with no path to unstick

A `Blocked` or `Rejected` row that stops at "file X doesn't exist on target" leaves the user to find the prerequisites; run unblock discovery ([unblock-discovery.md](references/unblock-discovery.md)) unless the rejection is intrinsic.
