# Input Detection

When a request carries a ticket, issue, or PR reference in natural language or
as an argument, detect the source and fetch context before classifying.

| Input pattern | Source | Action |
|---|---|---|
| `sc-12345` or `SC-12345` | Shortcut story | Shortcut REST `/stories/12345` |
| `https://app.shortcut.com/...` | Shortcut URL | Extract the story or epic ID, query REST |
| `#12345` or `12345` with repo context | GitHub issue or PR | `gh issue view` or `gh pr view` |
| `owner/repo#12345` | GitHub issue or PR | `gh issue view 12345 -R owner/repo` |
| `https://github.com/...` | GitHub URL | `gh issue view <url>` or `gh pr view <url>` |

For Shortcut REST calls, follow `rules/shortcut-api.md` and
`skills/shortcut/references/fetch.md`. Keep fetched IDs and customer context in
local files only.
