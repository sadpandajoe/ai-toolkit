---
name: workflows
description: Run AI Toolkit's goal workflows when the user asks for one of their outcomes — fix a bug, add a feature, review a branch (fixing by default) or a PR, fix CI, address PR feedback, test or watch a PR, validate a plan, create or update tests, save or resume workflow state, or report toolkit metrics, cost, and health. Use when the user asks to add or change behavior in a repository (load it before the first edit) or names one of these workflows. Do NOT use for a question or explanation about these topics, a diagnosis the user asked not to act on, a small direct answer, or a request a narrower domain skill fully covers.
---

# Goal Workflows

Pick the workflow whose outcome the user asked for from the summaries in
[the core manifest](../../interfaces/workflows.json); triggers are sample
phrasings, not keywords. A question, an explanation, or a problem described
without asking for a change gets your assessment, not a workflow that edits,
pushes, or posts; offer the workflow if acting would help. "Review this and
fix" is `review-code` with remediation; "don't change anything" is
review-only. Ask when two equally specific triggers tie. State `Workflow
entered: <name>` (or `none — <why>`) before any edit.

`bin/aitk list --details --json` (add `--with-pgm` when PGM is installed)
returns each workflow's reference, rules, dependencies, and gates: load
exactly those, and the domain skills it names when their phase starts. An
entry that names a command runs that command and presents its output. Gates
follow `rules/gates.md`; model routes follow `rules/orchestration.md` and
`rules/model-assignment.md`. A binding never authorizes a model or effort
downgrade.
