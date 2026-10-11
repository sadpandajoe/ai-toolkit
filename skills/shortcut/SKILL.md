---
name: shortcut
description: "Use for Shortcut story, epic, iteration, comment, evidence, and PR-link operations. Do NOT use for GitHub-only work, local project state, or product-code changes."
---

# Shortcut

Shortcut work splits into two phases:

| Phase | When | Reference |
|-------|------|-----------|
| Fetch | Need story, epic, iteration, workflow, member, or search data | [references/fetch.md](references/fetch.md) |
| Report | Need to post QA/fix/test results, upload evidence, update metadata, or link PRs | [references/report.md](references/report.md) |

## Notes

- A request carrying `sc-12345`, `SC-12345`, or a Shortcut URL uses Shortcut REST first.
- Never report a Shortcut API failure after a single failed call; the first call of a session may fail transiently.
- REST is preferred for repeatable workflow automation. Make every call through `<skill-dir>/scripts/sc.sh` (`get`, `post`, `put`, `upload`, `search`; resolve `<skill-dir>` from the installed shortcut skill): it sends the token header, retries once, and prints JSON that `jq` can read. There is no `aitk shortcut` command.
- Use `$SHORTCUT_API_TOKEN` by name only; never copy token values into prompts, rules, comments, or generated files.
- Global rules only route Shortcut work here. The detailed retry, parsing, field-shape, and posting protocols live in the references.
