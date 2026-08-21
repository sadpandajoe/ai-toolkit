---
name: workflows
description: Run AI Toolkit's daily feature, bug, CI, testing, QA, code-review, plan-review, PR, checkpoint, metrics, or maintenance workflows. Use for end-to-end software work and natural-language requests matching those workflows. Do NOT use for a small direct answer or when a narrower domain skill completely covers the request.
---

# Daily Workflows

This is the provider-neutral public router. Workflow identity and routing data
come only from [the core manifest](../../interfaces/workflows.json); this skill
does not maintain a second workflow table.

1. Read the manifest and match either the explicitly requested workflow name or
   the highest-specificity natural-language trigger.
2. If no workflow matches, handle the request directly. If equally specific
   triggers name different workflows, ask for the intended workflow.
3. Confirm the manifest owner is `workflows` and join its `reference_root` with
   `<workflow.name>.md`. Reject absolute paths or traversal.
4. Load exactly that canonical reference, its declared rules, and only the
   logical domain-skill dependencies it names. Resolve domain skills through
   `interfaces/skills.json` against the toolkit/package root, never relative to
   an installed symlink.
5. Read `interfaces/providers.json`, select the current provider, and load the
   binding document declared for any capability the workflow uses. A binding is
   operational only after that document is loaded; do not infer syntax from a
   different provider.
<!-- aitk-model-route-exempt:meta-routing-policy -->
6. Before dispatching any model worker, read `rules/model-assignment.md`, choose
   a stable route named by the canonical workflow/reference, resolve it with
   `<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, and launch it
   with the same boundary through the provider's `routed_subagent`. Routed
   workers never rely on ambient skill loading — see
   `rules/routed-subagent-integrity.md` for contract-closure and integrity
   mechanics.
   `fresh_subagent`, `parallel_fanout`, or `independent_review`
   describe isolation/scheduling; they never authorize an unpinned generic
   worker or a model/effort downgrade.
7. Preserve the selected workflow's authorization, state, verification, and
   reporting contract. Durable state uses the artifacts declared in
   `interfaces/contracts.json`; provider-native task state is only a disposable
   mirror.

This skill and natural-language routing are the public workflow interface.
