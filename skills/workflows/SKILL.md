---
name: workflows
description: Run AI Toolkit's daily testing, QA, code-review, plan-review, PR, checkpoint, metrics, or maintenance workflows. Use for end-to-end software work and natural-language requests matching those workflows. Do NOT use for a small direct answer or when a narrower domain skill completely covers the request.
---

# Daily Workflows

This is the provider-neutral public router. Workflow identity and routing data
come only from [the core manifest](../../interfaces/workflows.json); this skill
does not maintain a second workflow table.

`fix-bug` requests match `skills/goals/fix-bug/SKILL.md` directly by its own,
more specific skill description — this router's own "Do NOT use... when a
narrower domain skill completely covers the request" clause defers to it. This
router's `fix-bug` reference entry (`interfaces/workflows.json`,
`skills/workflows/references/fix-bug.md`) is retained only as literal
`fix-bug`-command-name compatibility until Wave 8 deletes it.

`create-feature` requests match `skills/goals/create-feature/SKILL.md`
directly by its own, more specific skill description, same pattern as
`fix-bug` above. The `interfaces/workflows.json` `create-feature` entry and
its reference file stay in place — durable-contract infrastructure, not
dispatch (see `fix-bug`'s note above).

`fix-ci` requests match `skills/goals/fix-ci/SKILL.md` directly by its own,
more specific skill description, same pattern as `fix-bug` above. The
`interfaces/workflows.json` `fix-ci` entry and its reference file stay in
place — durable-contract infrastructure, not dispatch.

Dual-run note: `review-code`, `review-code-adversarial`, and `review-pr`
requests can also match `skills/goals/code-review/SKILL.md` directly by its
own skill description — one goal skill covers all three manifest workflows,
same pattern as `fix-bug` above. This router stays the live dispatch path for
all three until `code-review`'s own Notes section confirms migration.

Dual-run note: `address-feedback` requests can also match
`skills/goals/address-feedback/SKILL.md` directly by its own skill
description — same pattern as `fix-bug` above. This router stays the live
dispatch path until that skill's own Notes section confirms migration.

Dual-run note: `test-pr` requests can also match
`skills/goals/test-pr/SKILL.md` directly by its own skill description —
same pattern as `fix-bug` above. This router stays the live dispatch path
until that skill's own Notes section confirms migration.

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
   a stable route named by the canonical workflow/reference, and check the
   provider's `routed_subagent` binding mode (loaded in step 5). When the
   binding is `native`, look up the worker by name — the matching file under
   `agents/claude/` — whose own frontmatter carries the route's
   model/permission restrictions, so no separate resolve/launch step runs.
   When the binding is `fallback`, resolve it with
   `<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, and launch it
   with the same boundary through that transport. The runner derives and
   inlines the exact contract closure from that inventoried boundary;
   per-file digests identify the transmitted content for diagnostics but are
   not an independently anchored integrity gate. Routed workers never rely on
   ambient skill loading.
   `fresh_subagent`, `parallel_fanout`, or `independent_review`
   describe isolation/scheduling; they never authorize an unpinned generic
   worker or a model/effort downgrade.
7. Preserve the selected workflow's authorization, state, verification, and
   reporting contract. Durable state uses the artifacts declared in
   `interfaces/contracts.json`; provider-native task state is only a disposable
   mirror.

This skill and natural-language routing are the public workflow interface.
