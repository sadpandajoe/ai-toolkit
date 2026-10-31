---
name: shortcut
description: Read and write Shortcut stories, epics, iterations, comments, evidence uploads and PR links through the Shortcut REST API. Use whenever a request carries sc-12345, SC-12345 or an app.shortcut.com URL, or results need to land on a story. Do NOT use for GitHub-only work, local notes, or product-code changes.
---

# Shortcut

Make every REST call through `<skill-dir>/scripts/sc.sh` (`get`, `post`,
`put`, `upload`, `search`); never hand-write curl or a retry wrapper. It needs
`$SHORTCUT_API_TOKEN`: use it by name only, never copy its value anywhere.

- References: `sc-12345` or `SC-12345` is story 12345; an
  `https://app.shortcut.com/...` URL carries a story or epic ID.
- The first call of a session can fail transiently (`organization2_missing`);
  `sc.sh` retries once. Exit 1 means the retry failed too: report the gap,
  never continue with missing data.
- Reading: [references/fetch.md](references/fetch.md) (field shapes,
  endpoints, search).
- Writing (comments, evidence, PR links, state):
  [references/post.md](references/post.md).
- Keep story IDs and customer context in local notes; they stay off public
  surfaces.
