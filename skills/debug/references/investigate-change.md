# Investigate Change

Use this phase when a workflow needs investigation or root-cause analysis as an internal step rather than as a standalone user-facing command: code-level behavior investigation, local root-cause analysis, checking whether a suspected fix already exists, or narrowing failure scope before planning or adaptation. The public action is still `fix-bug`, `create-feature`, or another end-to-end command.

## Goal

Find what is broken and why, with evidence strong enough for the RCA gate
([review-rca.md](review-rca.md)). The PASS list, the investigation steps (git
history scoped to the main branch and the current branch, the
`git show <sha>^:<file>` tip, incident versus latent bugs) and the RCA record
live in `agents/specialists/rca.md`; the debugger worker applies that contract
in producing mode, and the parent follows it when investigating inline.

Also check whether an equivalent fix already exists
([check-existing-fix.md](check-existing-fix.md)), and carry the incident versus
latent split into `PROJECT.md` and a later bug-fix PR description:
**Incident Root Cause**, **Latent Bugs / Hardening** when present, then
**Fix**.

## Output

The RCA record from `agents/specialists/rca.md`, plus
`Existing fix: <none found, or the commit or PR>`.
