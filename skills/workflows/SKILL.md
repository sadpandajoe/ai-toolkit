---
name: workflows
description: Run AI Toolkit's goal workflows from plain language — fix a bug, add a feature, review or review-and-fix a branch or PR, fix CI, address PR feedback, test a PR, watch a PR, validate a plan, create or update tests, checkpoint, metrics, or maintenance. Use for end-to-end software work and natural-language requests matching those workflows. Do NOT use for a small direct answer or when a narrower domain skill completely covers the request.
---

# Goal Workflows

The public router. Workflow identity and routing data come only from
[the core manifest](../../interfaces/workflows.json); this skill keeps no second
table. The parent session (Sonnet on Claude, Sol on Codex) runs the selected
workflow as a thin goal loop: classify, persist the routing snapshot, evaluate
the gate, run the next bounded capability, record the handoff, repeat.

1. Read the manifest and match the explicitly requested workflow name or the
   highest-specificity natural-language trigger. "Review this and fix" means
   `review-code` with remediation; "don't change anything" means review-only.
2. If no workflow matches, handle the request directly. If equally specific
   triggers name different workflows, ask which one.
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
