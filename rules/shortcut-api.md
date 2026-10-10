# Shortcut REST API

Routing constraints for Shortcut work. The detailed REST protocol lives in `skills/shortcut/`.

## Rules

- When a command receives `sc-12345`, `SC-12345`, or a Shortcut URL, use Shortcut REST first.
- Read `skills/shortcut/references/fetch.md` before making Shortcut REST calls.
- Never report a Shortcut API failure after a single failed call; the first call of a session may fail transiently.
- Use `$SHORTCUT_API_TOKEN` by name only. Do not put secrets in prompts, rules, comments, or generated files.

## Key Pointers

- API retry wrapper, JSON parsing, field shapes: `skills/shortcut/references/fetch.md`
- Posting reports and uploading evidence: `skills/shortcut/references/report.md`
- Input routing from story IDs/URLs: `rules/input-detection.md`
