# Input Detection

When a command receives an argument, detect whether it is a structured
reference to fetch or a natural-language description to use directly:

| Input Pattern | Source | Action |
|---------------|--------|--------|
| `sc-12345` or `SC-12345` | Shortcut story | Query Shortcut REST API `/stories/12345` |
| `https://app.shortcut.com/...` | Shortcut URL | Extract story/epic ID, query REST API |
| `#12345` or `12345` (with repo context) | GitHub issue/PR | `gh issue view` or `gh pr view` |
| `owner/repo#12345` | GitHub issue/PR | `gh issue view 12345 -R owner/repo` |
| `https://github.com/...` | GitHub URL | `gh issue view <url>` or `gh pr view <url>` |
| Anything matching none of the above | Natural-language request | Use the text as the goal description directly — there is nothing to fetch. This is the common case: "fix the bug where...", "add a setting for...". |

For Shortcut REST calls, follow `rules/shortcut-api.md` for routing and `skills/shortcut/references/fetch.md` for retry wrapper, JSON parsing, field shapes, and implementation details.

This rule only decides *fetch vs. use-as-is* for whatever argument a command
already received. Deciding *which* command or skill runs for a natural-language
request is a separate, upstream concern owned by skill descriptions —
`rules/universal.md`'s Agent Context Model — not by this file.
