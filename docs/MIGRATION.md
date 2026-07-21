# 0.2.0 Skills-Only Migration

Version 0.2.0 removes AI Toolkit's generated Claude slash aliases. Canonical
workflow behavior remains in `skills/workflows/references/`, registered by
`interfaces/workflows.json`, and exposed through the `workflows` Agent Skill.

## Invocation changes

Use a natural-language request or explicitly invoke the router:

```text
Fix this bug: pagination skips rows after an update
$workflows fix-bug "pagination skips rows after an update"

Review my local changes
$workflows review-code

Create a current program status report
$pgm create-status-report
```

For every former core `/name [args]` alias, the direct migration is
`$workflows name [args]`. Optional PGM aliases migrate to `$pgm name [args]`.
Claude's built-in commands, including `/review`, are not owned or changed by AI
Toolkit.

## Updating a source-linked install

```bash
git pull
./install.sh              # add --with-pgm when needed
bin/aitk doctor --strict
bin/aitk doctor --installed --strict
```

The installer removes old per-command links only when the ownership ledger
records them as toolkit-owned. It also migrates the old whole-directory
`.claude/commands` link when it points at this toolkit's legacy generated
output. Unrelated personal commands and directories are preserved. Existing
ignored `build/commands/` output may remain as one-level rollback material; it
is not installed or treated as a public interface in 0.2.0.

Use `bin/aitk uninstall` to remove matching owned artifacts or `bin/aitk
rollback` to restore the last exact install/upgrade/uninstall transaction.
Manual deletion loses recovery evidence and is not the supported lifecycle.

## Contributor changes

- Add or edit canonical workflow references under
  `skills/workflows/references/` and register routing metadata in
  `interfaces/workflows.json`.
- Keep shared `SKILL.md` frontmatter provider-neutral. Put Codex invocation
  policy in `skills/<name>/agents/openai.yaml` and provider-specific behavior in
  adapters.
- Run `bin/aitk build --with-pgm` to validate core and optional manifests and
  regenerate path-resolved provider guidance.
- Run `bin/aitk check` and `git diff --check` before handoff.

PGM remains source-linked-only in 0.2.0; the Codex plugin distribution contains
the core `skills/` tree and does not advertise `$pgm`.

Existing hand-written continuation blocks should be reinitialized with
`bin/aitk checkpoint init --workflow <name> --replace`. Normal init is a no-op
when the same valid workflow already owns the artifact, and replacement refuses
while any effect remains pending.
