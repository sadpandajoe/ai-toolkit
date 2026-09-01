---
name: workflows
description: Run AI Toolkit's daily testing, QA, plan-review, PR, checkpoint, metrics, or maintenance workflows. Use for end-to-end software work and natural-language requests matching those workflows. Do NOT use for a small direct answer or when a narrower domain skill completely covers the request.
---

# Daily Workflows

This is the provider-neutral public router. Workflow identity and routing data
come only from [the core manifest](../../interfaces/workflows.json); this skill
does not maintain a second workflow table.

Every manifest entry below is owned by a goal skill: its natural-language
description already matches these requests more specifically than this
router's own, so Claude Code's skill selection dispatches there directly —
this router's own "Do NOT use... when a narrower domain skill completely
covers the request" clause defers to it. Each entry's `reference` field
points straight at that goal skill's `SKILL.md`, so there is no separate
duplicate reference file to keep in sync.

| Workflow(s) | Goal skill |
|---|---|
| `fix-bug` | `skills/goals/fix-bug/SKILL.md` |
| `create-feature` | `skills/goals/create-feature/SKILL.md` |
| `fix-ci` | `skills/goals/fix-ci/SKILL.md` |
| `review-code`, `review-code-adversarial` | `skills/goals/code-review/SKILL.md` |
| `address-feedback` | `skills/goals/address-feedback/SKILL.md` |
| `test-pr` | `skills/goals/test-pr/SKILL.md` |
| `cherry-pick` | `skills/goals/cherry-pick/SKILL.md` |
| `refactor` | `skills/goals/refactor/SKILL.md` |
| `release-prep` | `skills/goals/release-prep/SKILL.md` |
| `watch-pr` | `skills/goals/watch-pr/SKILL.md` |

`review-pr` is not in this table: its contract effect (`external_effect`)
differs from `review-code`/`review-code-adversarial`'s (`git_mutation`), so it
cannot share `code-review/SKILL.md`'s single `## Effect Boundary` marker. It
keeps its own `skills/workflows/references/review-pr.md` reference and is
dispatched by this router like any other utility workflow below.
`create-pr`, a utility workflow with no goal-skill counterpart, keeps `PR` in
this router's own frontmatter description above.

1. Read the manifest and match either the explicitly requested workflow name or
   the highest-specificity natural-language trigger. If the matched workflow
   is one of the goal-owned names in the table above, stop here and dispatch
   to that workflow's goal skill instead. Do not proceed to step 3 for these —
   their manifest entry's `reference` already points at the goal skill, not a
   router-owned reference file.
2. If no workflow matches, handle the request directly. If equally specific
   triggers name different workflows, ask for the intended workflow.
3. Resolve the matched workflow's `reference` field from the manifest entry
   (falling back to `<reference_root>/<workflow.name>.md` when a workflow
   declares no explicit `reference`). Reject absolute paths or traversal.
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
