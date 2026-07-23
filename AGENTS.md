# AI Toolkit Development

- Canonical daily workflow behavior lives in `skills/workflows/references/` and is registered in `interfaces/workflows.json`.
- `bin/aitk build` generates only path-resolved provider guidance; workflow behavior comes from skills and manifests.
- Use `bin/aitk build --with-pgm` to validate the bundled PGM extension alongside core interfaces.
- Shared `SKILL.md` frontmatter contains only `name` and `description`. Put Codex UI/invocation policy in `agents/openai.yaml` and provider-specific behavior in adapters.
- Keep user configuration non-destructive and idempotent. Preserve unrelated files, guidance, skills, commands, and hooks.
- Before handing off a toolkit change, run `bin/aitk check` and `git diff --check`.
