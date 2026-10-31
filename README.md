# AI Toolkit

Skills, agents and safety hooks for AI-assisted software delivery on Claude
Code and Codex.

Current models already reproduce bugs, test red/green, scope their own work
and know when to ask. The toolkit doesn't tell them how to work. It gives them
what they can't know: Preset and Superset environments, CI quirks, past
incidents, your preferences. And it enforces the few things that must never
happen.

## Mental Model

- **Skills** (`skills/`) hold facts, one skill per outcome, triggered by the
  skill's description. There is no router.
- **Rules** (`rules/universal.md`) are the only always-on text: the
  authorization, safety, evidence and PII boundaries.
- **Hooks** (`hooks/`) enforce the boundaries deterministically, whatever the
  model reads.
- **Agents** (`agents/`) exist only where a fresh context pays for itself:
  `reviewer` (independence), `ci-investigator` and `qa-runner` (noisy logs and
  browser output kept out of the main session).
- **Second opinion**: `skills/review/scripts/second-opinion.py` asks the other
  model family (Codex from Claude Code, Claude from Codex) for a read-only
  review of a diff or a plan. The models are pinned at the top of that file.

Every line in the toolkit has to earn its place: a fact the model can't infer,
a boundary a hook enforces, a format code parses, or a portability shim
([AGENTS.md](AGENTS.md)).

## Install

Install it as a plugin. A marketplace added from a local checkout loads the
plugin in place on Claude Code, so edits reach the next session. Codex
installs a copy, which `codex plugin add` refreshes.

```bash
git clone https://github.com/sadpandajoe/ai-toolkit.git ~/opt/code/ai-toolkit
cd ~/opt/code/ai-toolkit
./setup.sh          # optional: claude, codex, node (asks before installing Homebrew)

# Claude Code: skills, agents and hooks ship in the plugin
claude plugin marketplace add ~/opt/code/ai-toolkit
claude plugin install ai-toolkit@ai-toolkit

# Codex: skills and hooks ship in the plugin; trust the hooks in /hooks afterwards
codex plugin marketplace add ~/opt/code/ai-toolkit
codex plugin add ai-toolkit@ai-toolkit
./install.sh        # links agents/codex/*.toml, which a Codex plugin cannot ship
```

`./install.sh` is idempotent and leaves files it didn't create alone;
`./install.sh --uninstall` removes only its own links.

A plugin can't ship `permissions`, so add these deny rules to
`~/.claude/settings.json` yourself if you want the git bypasses refused before
the hook sees them:

```json
"permissions": {"deny": ["Bash(git push --force *)", "Bash(git push -f *)", "Bash(git commit --no-verify *)", "Bash(git commit -n *)"]}
```

Requirements: Python 3.11 or newer for the git guard and the scripts, bash 3.2
or newer for the hooks, `gh` for the GitHub skills, and Node for the Preset
and QA scripts.

### Migrating from v0.3 (`bin/aitk install`)

The workflow engine (`bin/aitk`, `PROJECT.md` routing snapshots, gates, model
routing) is gone. Remove the old install before you install the plugin, using
the uninstaller from the last release that had it:

```bash
cd ~/opt/code/ai-toolkit
git checkout 0.3.0 && ./install.sh --uninstall
git checkout main
```

The session-start hook warns you if the old install is still in place.
Existing `PROJECT.md` files keep working as plain notes (see `handoff`).

## Skills

| Skill | Use it to |
|---|---|
| `fix-bug` | Fix a reported bug: evidenced root cause, regression test, draft PR |
| `build-feature` | Build a feature or other planned change end to end |
| `fix-ci` | Diagnose and fix failing CI, external checks included |
| `review` | Review a local change or someone's PR; get a second opinion |
| `address-feedback` | Work through review comments on your own PR |
| `create-pr` | Push and open a draft PR with a readable title and body |
| `watch-pr` | Watch a PR unattended until it's green and quiet |
| `test-pr` | Test a PR or test plan in a running app, with screenshots and video |
| `cherry-pick` | Backport commits or PRs, one at a time or in batches; release audits |
| `handoff` | Keep `PROJECT.md` notes for work that spans sessions |
| `shortcut` | Read and write Shortcut stories, comments and uploads |
| `superset-local` | Start a local Superset stack and run its Playwright specs |
| `preset-rbac-setup` | Seed the RBAC test users on a Preset staging or dev workspace |
| `pgm` | Program status and velocity reports (`extensions/pgm/`) |
| `agent-setup-maintainer` | Change this toolkit itself |

## Hooks

`hooks/hooks.json` is the one list; both plugins register it.

| Hook | Event | Behavior |
|---|---|---|
| `session-start.sh` | SessionStart | Prints the toolkit root and `rules/universal.md`; warns once when a v0.3 install is still in place |
| `prevent-project-commit.sh` | PreToolUse (Bash) | Runs `hooks/lib/git_guard.py`: blocks `--no-verify` and other hook bypasses, force-pushing or deleting `main`/`master`, commits of local notes (`PROJECT.md`, `PLAN.md`, `WATCH.md`, `CHERRY_PICK.md`, `CI_FIX.md`, `PROJECT_ARCHIVE.md`) or `.ai-toolkit/`, and a non-draft `gh pr create`, `gh pr ready` or `gh pr merge` unless the user started the session with `AITK_PR_READY=1`; a command that sets or exports `AITK_PR_READY` or `SKIP_PRECHECK` itself is blocked |
| `pre-push-validate.sh` | PreToolUse (Bash) | Runs the repository's pre-commit (from the repo venv when it has one, or ruff) on changed files and pytest on changed test files before a push; a check past its time budget warns instead of blocking; `SKIP_PRECHECK=1` in the session environment skips it |

The git guard fails closed: without python3 it blocks git and `gh` commands
rather than let them through. To turn the hooks off, Codex can disable each one
in `/hooks`, or all of them with `hooks = false` under `[features]` in
`config.toml`. Claude Code has no per-plugin hook switch, only
`"disableAllHooks": true` in settings or disabling the plugin.

## Scripts

- `python3 scripts/show-cost.py [today|<N>d|month|all|YYYY-MM-DD]`: token
  usage and API-equivalent cost from Claude Code sessions, subagents
  included. Codex keeps no usage records, and unknown models stay unpriced.
- `statusline/statusline-command.sh`: an optional Claude Code status line
  (model, effort, session length, cost, context and rate-limit bars, branch).
  Point `statusLine` in `~/.claude/settings.json` at it:
  `{"type": "command", "command": "bash ~/opt/code/ai-toolkit/statusline/statusline-command.sh"}`.
  It needs `jq`.
- `scripts/plugin-proof.sh claude|codex`: installs the plugin into a scratch
  HOME and checks with real model turns that the rules, agents, skills and git
  guard reach a session.

## Development

See [AGENTS.md](AGENTS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Before handing off a change:

```bash
python3 scripts/check.py
python3 -m unittest discover -s tests
git diff --check
```
