# /toolkit-doctor - Structural Health Check

> **When**: After install, after editing source files, or as a regression gate at the end of each wave.
> **Produces**: Diagnostic report with PASS/FAIL/DRIFT/SKIP verdicts and a summary line.

No `@`-imports — this command is standalone so it can run even when the toolkit is unhealthy.

## Output Format

Emit one line per check:

```
[PASS] Description
[FAIL] Description
       Detail (indented)
[DRIFT] Description
        Detail (indented)
[SKIP] Description — reason
```

- **FAIL** — broken symlink, stale build, path leak, broken import. The toolkit will malfunction.
- **DRIFT** — README out of sync with reality. Misleading but not broken.
- **SKIP** — check deferred or not applicable.

End with: `toolkit-doctor: X checks — Y PASS, Z FAIL, W DRIFT, V SKIP`

## Steps

### 1. Resolve Paths

Determine these root paths (all subsequent checks use them):
- `REPO_DIR`: git root of the ai-toolkit repo (`git rev-parse --show-toplevel`)
- `CLAUDE_DIR`: `~/.claude`
- `CODEX_DIR`: `~/.codex`

### 2. Run Checks

#### A. Symlink Health

For each expected symlink, verify it exists, is a symlink, and points to the correct target:

| Symlink | Expected Target |
|---------|----------------|
| `$CLAUDE_DIR/CLAUDE.md` | `$REPO_DIR/build/config/CLAUDE.md` |
| `$CLAUDE_DIR/commands` | `$REPO_DIR/build/commands` |
| `$CLAUDE_DIR/skills` | `$REPO_DIR/skills` |

Then iterate each installable skill under `$REPO_DIR/skills/` and verify a matching symlink exists in `$CODEX_DIR/skills/` pointing to the correct source. Installable skills are top-level directories with `SKILL.md` plus any remaining top-level `*.md` skills. Do not hardcode skill names — discover them from the filesystem.

Verify no legacy persona subdirectories remain under `$REPO_DIR/skills/`. Directory skills are valid only when they contain `SKILL.md`.

Finally, verify no symlink target is dangling (target file/dir must exist on disk).

#### B. Build Freshness

1. `$REPO_DIR/build/` directory exists
2. Grep all files under `build/` for the literal string `{{TOOLKIT_DIR}}` — any match is FAIL (template not resolved)
3. Compare the set of `*.md` filenames in `build/commands/` against `commands/` — must match exactly (same names, same count)

#### C. Path Leaks

Grep checked-in source files under `commands/`, `config/`, and `rules/` for paths matching `/Users/` or `/home/`. Any match is FAIL — show the file and line.

Exclude `build/` (those are resolved copies, not source).

#### D. Import Validity

1. **Source imports**: Extract all `@{{TOOLKIT_DIR}}/path` references from files in `commands/` and `config/`. For each, verify `$REPO_DIR/path` exists on disk.
2. **Build imports**: Extract all `@/absolute/path` references from files in `build/commands/` and `build/config/`. For each, verify the absolute path exists on disk.
3. **Skill imports from commands**: In `commands/`, any source import that resolves under `skills/` is DRIFT. Commands should import only short rules needed immediately, then name or link skill phases for lazy loading.

#### E. Structural Inventory

Compare README.md content against the actual filesystem. Each mismatch is DRIFT, not FAIL.

1. **Commands**: Every `*.md` in `commands/` should appear in the README Repository Structure block. Every command listed in the block should exist on disk. Bidirectional check.
2. **Rules**: Same bidirectional check for `rules/*.md` against the README rules tree.
3. **Skills**: Every installable skill under `skills/` should appear in the README skills tree. Bidirectional check.
4. **Workflow Rules table**: Every `rules/*.md` file referenced in the Workflow Rules table should exist on disk.

#### F. Extension Boundaries

1. **Core isolation**: Grep all files under `commands/`, `config/`, `rules/`, `skills/` for paths starting with `extensions/`. Any match is FAIL — core files must not reference extension paths.
2. **Extension self-containment**: If `extensions/pgm/` exists, verify its files only reference their own tree or core paths (not other extensions).
3. **PGM install state**: If PGM is installed (commands exist in `build/commands/`), verify the extension commands resolve. If not installed, verify no PGM commands appear in `build/commands/`.

#### G. Skill Cross-References

For each `skills/*/SKILL.md` (and any flat `skills/*.md`), verify the skill's internal structure resolves. All checks here are FAIL when broken — a missing reference means the skill is silently broken at invocation time.

1. **Reference link resolution.** Extract every markdown link in `SKILL.md` matching `references/*.md`, `templates/*.md`, `examples/*.md`, `assets/*`, or `scripts/*`. For each, verify the target file exists relative to the skill folder.
2. **Reference orphans.** For each `references/*.md` file in the skill folder, verify it is linked from `SKILL.md` (or another reference within the same skill). Unlinked references are DRIFT — they bloat the skill folder without participating in the routing table.
3. **Description boundaries.** Each `SKILL.md` description must contain both a "Use when" / "Use for" trigger phrase **and** a "Do NOT use" boundary clause. Missing either is DRIFT — the description is then a poor classifier.
4. **Capitalization consistency.** Files named `GOTCHAS.md`, `LESSONS.md`, or `RULES.md` (uppercase) are DRIFT — the convention is lowercase `gotchas.md`, `lessons.md`, `rules.md` to match the "Before Starting" line in every SKILL.md.

#### H. Permission Health

Read `$CLAUDE_DIR/settings.json` if it exists. If it does not exist, emit `[SKIP] Permission health — no settings.json found` and move on.

1. **Core permissions**: Check that the `permissions.allow` array contains these commonly needed entries. Emit DRIFT for each missing entry:
   - `Bash(git commit:*)` — needed by all commit workflows
   - `Bash(git add:*)` — needed by all staging workflows
   - `Bash(gh pr:*)` — needed by `/review-pr`, `/address-feedback`
   - `Bash(gh api:*)` — needed by PR and issue operations

2. **Hook status**: If `$REPO_DIR/hooks/` directory exists but `settings.json` has no `hooks` key, emit DRIFT: `"Hooks available but not installed. Run ./install-hooks.sh"`

All checks in this section are DRIFT (recommendations), never FAIL.

#### I. Runtime Capabilities

Check for optional external tools that specific commands depend on. All checks are **DRIFT** (never FAIL) since these are optional capabilities.

| Capability | How to check | Commands that need it |
|------------|-------------|----------------------|
| **GitHub CLI** | `gh auth status` succeeds | `/review-pr`, `/address-feedback`, `/create-pr` |
| **Codex plugin** | `/codex:setup` is a recognized command in the session | `/review-code` (always-on Codex second-opinion lane), `/review-code-adversarial`, `/review-pr` (Lane 2) |
| **jq** | `command -v jq` succeeds | `install-hooks.sh`, hooks |
| **Python 3** | `command -v python3` succeeds | git safety hook parsing |
| **Playwright MCP** | Playwright MCP tools are available in the session | `/run-test-plan` (UI testing) |

For each capability:
- If available: `[PASS] {name}`
- If unavailable: `[DRIFT] {name} — not available. Needed by: {commands}. Install: {instructions}`

If none of the checks can be performed (e.g., running outside a live session), emit `[SKIP] Runtime capabilities — cannot verify outside a live session`.

### 3. Summary

Count results by category and emit:

```
toolkit-doctor: X checks — Y PASS, Z FAIL, W DRIFT, V SKIP
```

If any FAIL: `"Run install.sh to rebuild, or investigate the failures above."`
If only DRIFT: `"README is out of sync with reality. Update README.md to match."`
If clean: `"All checks passed."`

## Notes
- Diagnose only — do not auto-fix anything
- Dynamic inventory — iterates the filesystem, not hardcoded file lists
- DRIFT is informational, not blocking — but target 0 DRIFT for each wave
- This command has no `@`-imports to avoid circular dependency on toolkit health
