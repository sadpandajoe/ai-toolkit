# Commands-to-Skills Migration

Version 0.1.0 changes the ownership model. Claude slash aliases remain only as
deprecated generated shims during migration.

## What changed

- The 25 files in `commands/` are generated adapters and no longer contain workflow procedures.
- Canonical procedures moved to `skills/workflows/references/` and are selected through the `workflows` skill.
- Codex and other Agent Skills-compatible runtimes can use natural-language requests or explicitly invoke `$workflows`.
- Claude users can temporarily continue using the same slash aliases, but new
  documentation and integrations should use natural language, `$workflows`,
  `$pgm`, or `bin/aitk`.
- Toolkit metrics now write to `.ai-toolkit/metrics.jsonl`; readers fall back to legacy `.claude/metrics.jsonl` during migration.
- Local workflow state protection now covers PROJECT, archive, plan, watch, cherry-pick, and CI manifests.
- The optional PGM reports now use their own manifest and canonical `pgm` Agent Skill; `--with-pgm` installs both generated aliases and the skill.
- PGM is source-linked-only in version 0.1.0; the Codex plugin distribution
  contains the core `skills/` tree and does not advertise `$pgm`.

## Updating a local install

```bash
git pull
./install.sh
bin/aitk doctor --strict
bin/aitk doctor --installed --strict
```

The installer migrates only exact legacy toolkit-owned links, records all new
ownership in `~/.ai-toolkit/install-state.json`, and preserves unrelated
commands, skills, and instructions. Internal support skills are no longer
linked into public discovery locations.

Use `bin/aitk uninstall` to remove matching owned artifacts or `bin/aitk
rollback` to restore the last exact install/upgrade/uninstall transaction.
Manual deletion loses recovery evidence and is not the supported lifecycle.

## Contributor action

Do not edit `commands/*.md`. Edit the canonical workflow reference and manifest, then run `bin/aitk build`. CI or `bin/aitk check` fails if a generated adapter drifts.

Provider-specific frontmatter was removed from shared `SKILL.md` files. Codex invocation policy now lives in `skills/<name>/agents/openai.yaml`; Claude compatibility comes from generated commands and its installed skill discovery.

If the PGM extension is installed, use `bin/aitk build --with-pgm --check`,
`bin/aitk list --with-pgm`, or `bin/aitk route --with-pgm`. Its reports must
pass `bin/aitk pgm-preflight` before collection. Running `./install.sh` without
the flag removes only ledger-owned PGM links and leaves unrelated user
configuration intact.

Existing hand-written continuation blocks should be reinitialized with
`bin/aitk checkpoint init --workflow <name> --replace`. Normal init is a no-op
when the same valid workflow already owns the artifact, so resuming cannot
erase progress. Replacement is explicit and refuses while any effect remains
pending. The v1 machine block is strict: malformed/stale state is refused
instead of guessed.
