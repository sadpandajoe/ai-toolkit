# AI Toolkit Development

- Canonical daily workflow behavior lives in `skills/workflows/references/` and is registered in `interfaces/workflows.json`.
- `commands/` is generated. Never edit command adapters directly; run `bin/aitk build` after changing the manifest.
- Optional extension commands are generated from their own manifest; use `bin/aitk build --with-pgm` for the bundled PGM extension.
- Shared `SKILL.md` frontmatter contains only `name` and `description`. Put Codex UI/invocation policy in `agents/openai.yaml` and provider-specific behavior in adapters.
- Keep user configuration non-destructive and idempotent. Preserve unrelated files, guidance, skills, commands, and hooks.
- Before handing off a toolkit change, run `bin/aitk check` and `git diff --check`.
