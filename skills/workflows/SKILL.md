---
name: workflows
description: Run AI Toolkit's goal workflows when the user asks for one of their outcomes — fix a bug, add a feature, review a branch (fixing by default) or a PR, fix CI, address PR feedback, test or watch a PR, validate a plan, create or update tests, save or resume workflow state, or report toolkit metrics, cost, and health. Use when the user asks to add or change behavior in a repository (load it before the first edit) or names one of these workflows. Do NOT use for a question or explanation about these topics, a diagnosis the user asked not to act on, a small direct answer, or a request a narrower domain skill fully covers.
---

# Goal Workflows

The public router. Workflow identity and routing data come only from
[the core manifest](../../interfaces/workflows.json); this skill keeps no second
table. The parent (orchestrating) session runs the selected
workflow as a thin goal loop: classify, persist the routing snapshot, evaluate
the gate, run the next bounded capability, record the handoff, repeat.

1. Read the manifest and pick the workflow whose outcome the user asked for,
   by name or from the summaries; triggers are sample phrasings, not
   keywords. When the user asks a question, asks for an explanation, or
   describes a problem without asking for a change, the deliverable is your
   assessment: answer it without starting a workflow that edits, pushes, or
   posts (a read-only workflow such as `verify` or `show-cost` may answer it),
   and offer the workflow if acting would help. For example, "how does code
   review work here" is not `review-code`, and "explain this CI failure" is
   not `fix-ci`. "Review this and fix" means `review-code` with remediation;
   "don't change anything" means review-only.
2. If no workflow fits, handle the request directly. If two workflows fit the
   asked-for outcome equally well, ask which one. Either way, state the
   outcome once as `Workflow entered: <name>` or `Workflow entered: none —
   <why>` before any edit; `none` persists no snapshot.
3. Confirm the manifest owner is `workflows` and join its `reference_root` with
   `<workflow.name>.md`. Reject absolute paths or traversal.
4. Load exactly that reference, its declared rules, and only the domain skills
   it names when their phase starts. Resolve skills through
   `interfaces/skills.json` against the toolkit root, never an installed
   symlink.
5. Read `interfaces/providers.json` and the current provider's binding document
   before using any capability (`fresh_subagent`, `independent_review`,
   `routed_subagent`, and the rest).
<!-- aitk-model-route-exempt:meta-routing-policy -->
6. Before dispatching any model worker, read `rules/orchestration.md` and
   `rules/model-assignment.md`, choose the stable route the reference names at
   its inventoried marker, and launch it through the provider binding: native
   toolkit agents for same-provider workers, `<toolkit-root>/bin/aitk
   model-route --boundary <marker-id>` plus `model-run` for specialists. The
   runner inlines the boundary's contract closure; routed workers never rely on
   ambient skills. A binding never authorizes an unpinned generic worker or a
   model or effort downgrade.
7. Preserve the workflow's authorization, state, verification, and reporting
   contract. Durable state is `PROJECT.md` (routing snapshot plus checkpoint)
   and the artifacts declared in `interfaces/contracts.json`; provider task
   lists are a disposable mirror. Gates follow `rules/gates.md`; only
   `USER_DECISION`, `BLOCKED`, and hard safety gates reach the user.

This skill and natural-language routing are the public workflow interface.
