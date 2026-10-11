# Resource Management

Check resources before consuming them (Docker, test workers, builds, agents);
parallel work shares one machine.

- Fit work to measured capacity, not to container count or CPU count. The
  Docker facts and thresholds live in
  `skills/workflows/references/check-resources.md`.
- Cap test workers explicitly: Jest's default worker count can OOM, so pass
  `--maxWorkers`; size pytest `-n` the same way; respect
  `playwright.config`'s worker strategy unless there is a clear reason not to.
- Run parallel workers as measured capacity allows, not a fixed two or three.
- Keep the agent tree bounded: the goal skill, one worker layer, and one
  exceptional specialist child (`rules/orchestration.md`).
- A git worktree shares `.git` but not dependencies, build outputs, or `.env`
  files: install, rebuild, or copy them before tests or builds there.
- Never change Docker Desktop settings programmatically; suggest the change to
  the user.
