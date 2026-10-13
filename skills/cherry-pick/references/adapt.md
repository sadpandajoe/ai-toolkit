# Cherry-Pick Adapt

Use when a cherry-pick cannot be applied mechanically. Preserve the source
change's behavior on the target branch without widening scope; batch ordering
and final validation happen elsewhere.

## Resolution Rules

- Modify/delete conflicts belong to apply (`git rm`); hand them back.
- Prefer adapting to the target branch's APIs over pulling in structural changes.
- Extract only the functional part of a mixed commit when possible.
- If a prerequisite change is truly required, stop and escalate; do not silently pull it in.
- Reject the cherry-pick if preserving source intent would require a broad refactor.
- Record the adaptation severity (`None`, `Minor`, `Medium`, `High`, defined in
  [the manifest template](../templates/cherry-pick-manifest.md)); dropping
  significant chunks is `High`, not `Minor`.

A dropped or trimmed bug fix can leave the bug live on the target: see
[gotchas.md](../gotchas.md), "Bug-fix dropped due to architecture mismatch".

## Scope Leak Detection During Resolution

Conflict resolution is the main active vector for scope leak: the source
branch's version of a conflicting region can carry changes from commits other
than the one being picked, and resolving toward it brings them in. The
post-apply audit in validate is defense in depth, not a substitute.

After resolving each conflicting file:

1. Get the source commit's diff for that file:
   `git diff <commit>^..<commit> -- <file>`.
2. Lines in your resolution that are neither in that diff nor already on the
   target are leak candidates.
3. Strip them, keeping only the picked commit's changes adapted to the
   target's context.

When unsure which commit a line came from, run
`git log --oneline <source-commit>..HEAD -- <file>` on the source branch.

## Escalation Triggers

Stop and ask when:

- there are two reasonable behavior-preserving interpretations;
- the adaptation changes externally visible behavior;
- the target lacks required architectural groundwork;
- dropping a bug fix leaves the bug unaddressed on the target (surface the
  residual risk even when proceeding);
- leak detection finds adjacent-commit changes that may be intentional
  prerequisites;
- a bundled PR has sub-fixes that look unrelated to the main fix. List the
  sub-fixes proposed for exclusion with a one-line reason each and let the
  orchestrator or the user confirm the drop; listing the PR usually means
  the user wants all of it.
