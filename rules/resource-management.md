# Resource Management

Check resources before consuming them (Docker, test workers, builds, agents),
and fit work to measured capacity, not to container count or CPU count;
parallel workers share the machine.

| Work | Read |
|---|---|
| Starting Docker or local app stacks | `skills/preflight/rules.md` |
| Entering or preparing a git worktree | `skills/preflight/rules.md` |
| Running Jest, pytest, Playwright, or similar suites | `skills/testing/rules.md` |
