# Investigation Principles

## Golden Rules
- [ ] **Document in PROJECT.md before proposing solutions** — include: problem statement, evidence gathered, root cause hypothesis, and how you confirmed it
- [ ] **Use git history first** — blame, log, bisect
- [ ] **Find root cause, not symptoms** — verify by writing a test that fails before the fix and passes after
- [ ] **Scope git searches to master + current branch** — do not use `git log --all`. Unmerged branches may contain experimental or unvetted code that was never shipped. When restoring removed or commented-out code, trace the removal commit on master, then inspect its parent (`git show <removal-sha>^:<file>`)
- [ ] **Parallelize when useful** — user-visible triage and code investigation can run together
- [ ] **Gather evidence** — logs, stack traces, reproduction steps
- [ ] **Verify assumptions** — dependencies, imports, file existence

When investigation is complete (root cause documented, evidence gathered,
approach clear), move to planning. STANDARD work produces `PLAN.md` through the
selected workflow; TRIVIAL or MODERATE work proceeds inline unless a
workflow-specific gate says otherwise.

## Common Mistakes

| Avoid | Do Instead |
|-------|------------|
| Jump to solutions | Understand problem first |
| Skip git history | Use blame/log liberally |
| Assume | Verify with commands |
| Patch symptoms | Fix root cause |
| Skip documentation | Document in PROJECT.md |
| `git log --all` for code to restore | Trace the removal commit on master, inspect parent |
| Pull code from unmerged branches | Use only master's history — unmerged code is unvetted |
| Classify CI from a check name, status string, or green check | Open the artifact behind it — see `rules/ci-evidence.md` |
