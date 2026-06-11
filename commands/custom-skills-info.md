# /custom-skills-info - Toolkit Reference Card

> **When**: You want to see what commands are available, what they do, and what gates they enforce.

Print the reference card below and stop. No investigation, no file reading — just output the table.

## Output

```markdown
## Toolkit Commands

### Workflow Starters
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/start` | Load session, resume from checkpoint | Beginning of any session | — |
| `/create-feature` | Full feature lifecycle: plan → review → implement → code review | New features, planned refactors | Complexity, Plan Review 8/10, Cold Read, Action Gate, Review Gate |
| `/fix-bug` | Full bug lifecycle: triage → RCA → fix → review → QA | Something is broken | Complexity, Action Gate, Review Gate |
| `/fix-ci` | Diagnose CI failure → classify → safe fix | CI build failed | Complexity, Review Gate |
| `/cherry-pick` | Plan, risk-assess, and apply cross-branch cherry-picks | Moving commits between branches | Action Gate per change |

### Quality & Testing
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/review-code` | Orchestrated team review: quality, architecture, tests, optional second opinion | Before commit, quality pass | Complexity, Review Gate |
| `/review-code-adversarial` | Adversarial red-team with optional second opinion | Security-sensitive changes | Adversarial Rating, Review Gate |
| `/review-plan` | Iterate plan reviewers to 8/10 | One-off plan quality check | All reviewers 8/10, Cold Read |
| `/create-tests` | Create first meaningful tests for untested area | No tests exist yet | Review Gate |
| `/update-tests` | Improve an existing test suite | Tests exist but need work | Review Gate |
| `/run-test-plan` | Derive/review test plan, execute, summarize | Validate without fixing | Plan score 8/10 |
| `/verify` | Run tests on changed files | Quick verification | — |

### Review & PR
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/review-pr` | Orchestrated team PR review: quality, tests, patterns, optional second opinion, recommendation/posting | Reviewing someone's PR | Complexity, recommendation gates |
| `/address-feedback` | Fix PR review comments, post replies | PR has review feedback | Complexity, Review Gate |
| `/create-pr` | Generate PR title + description from diff/commits | Ready to open a PR | — |
| `/watch-pr` | Loop on an open PR: fix CI failures, handle comments, escalate judgment calls | PR open, want unattended babysitting | Standing-auth boundary, escalation hard stops |

### Project State
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/checkpoint` | Save state to PROJECT.md — works for both quick logs (`/checkpoint "msg"`) and full save-and-clear (`/checkpoint --clear`) | Anytime you want to update state, log progress, or save before `/clear` | — |
| `/archive-project-file` | Move completed work to archive | PROJECT.md is cluttered | — |
| `/complete-project` | Capstone: summarize, promote learnings, archive, hand off | Project or major work is done | — |

### Reflection & Memory
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/reflect` | Add/list/review/prune/failure/promote memories and rules | Capture patterns, postmortems, promote to rules | — |
| `/metrics` | Summarize workflow pass rates, rounds, model usage | Understand workflow performance | — |

### Maintenance
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/toolkit-doctor` | Validate symlinks, imports, paths, permissions, extensions | After install, after edits | — |

Note: agent-setup audits now happen automatically — the `agent-setup-edit-reminder` PostToolUse hook activates the `agent-setup-maintainer` skill whenever an agent-setup file is edited.

### Extension (PGM) — install with `--with-pgm`
| Command | What it does | When to call | Gates |
|---------|-------------|-------------|-------|
| `/create-status-report` | Live program health from Shortcut + GitHub | Before meetings, check-ins | — |
| `/create-velocity-report` | Monthly velocity metrics | End of month | — |
```

## Notes
- This is a static reference card — update it when commands change
- For detailed usage of any command, run it with no arguments or read its command file
- Gates marked "—" means the command has no enforced quality gates (it's a utility)
