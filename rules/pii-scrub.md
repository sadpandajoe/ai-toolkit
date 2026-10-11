# PII Scrub

Public surfaces are permanent: PR titles and bodies, review replies, comments,
and commit messages survive later edits in git history, mirrors, notification
emails, and search indexes. Before posting one, re-read the text and rewrite
generically:

- **Customer or workspace names**: describe the configuration ("dashboards with
  `hideTab: true`") or say "a customer".
- **Ticket IDs**: Shortcut (`sc-XXXXX`), Linear, Jira, other internal trackers.
  They belong in `PROJECT.md`, a local commit footer, or an internal channel.
- **Internal URLs**: tracker links, internal dashboards, staging workspaces,
  customer-specific instances.
- **Reporter identity**: the customer, support engineer, or internal user who
  reported the problem.
- **Credentials and connection strings**, even in repro snippets and test
  plans: use placeholders.

The rule holds in a private repository too, because the audience is broader
than the current team. Local files and chat summaries may carry the IDs.

After a rewrite, check that the text still does its job: the PR body still
describes the change, the reply still answers the reviewer. Pause for the
user's confirmation only when the scrub rewrote something (show the rewrite)
or when `--step` was passed; otherwise continue.
