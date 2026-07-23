# Agent Setup Maintainer Lessons

## `create-feature` Is The Current Workflow Pattern

Use `skills/workflows/references/create-feature.md` as the reference shape when
refactoring long-running workflows. The canonical skill reference is the
behavior owner.

Good workflow shape:

- Header imports only the short rules the main thread needs immediately.
- The canonical reference keeps visible gates, path rules, and final stop conditions.
- Workflow-specific complexity signals stay in the reference.
- A short happy path appears before any dense routing table.
- Step routing names the owner, route, and load/handoff condition.
- Skills and references load only at phase entry.
- Subagents return compact handoffs; the main thread writes durable state (`PROJECT.md`, `PLAN.md`, manifests).
- TRIVIAL paths stay inline; if reviewer subagents are needed, reclassify as MODERATE.
- MODERATE paths run inline-first with the `verify` workflow or equivalent preflight before review.
- STANDARD paths, including workstream-shaped work, use fresh reviewer subagents after material revisions and bounded implementation handoffs.
- STANDARD paths checkpoint and apply `context_reset` at major phase boundaries after durable artifacts are current; files are the memory, chat is disposable.
- Implementation stays inline by default; delegate only when isolation, fresh context, or real parallelism helps.
- Review Gate skip/micro-fix exceptions are explicit and never replace review for meaningful logic changes.

Avoid:

- Header-importing skills, long references, templates, or examples.
- Splitting ownership and routing into separate sections that can drift.
- Letting subagents update `PROJECT.md` or `PLAN.md` directly.
- Moving workflow-owned end-to-end flows into a domain skill whose boundary says it should not own that work.

When auditing another workflow, compare it to `create-feature` before inventing a new structure.

## Cross-agent skill handoff: the spawn prompt is the only guaranteed channel (2026-06-10, Princeton workspace)

<!-- aitk-model-route-exempt:historical-handoff-lesson -->
When an orchestrator skill hands work to a spawned worker agent, do not hand it file pointers — relative paths don't resolve from the worker's cwd, and absolute paths assume the worker's user/sandbox can read the orchestrator's workspace (codex sandboxes file reads to its workdir; per-session unix users/groups are common in orchestration platforms). The first fix attempt here used absolute paths and was still wrong. Ship the contract inline in the spawn prompt: contract file verbatim + per-topic digests (only the receiver-relevant sections — skip routing/boundary sections the orchestrator already consumed). Measure the payload before assuming inlining is too costly (here: 8–13k tokens against a session that reads a full PR diff). Pair the handoff with a loud-failure rule (exact error string on malformed payload, no improvisation) — otherwise workers silently improvise a degraded contract and the output looks normal. A deferred smoke test on a handoff design ships the breakage. Also grep for inline *copies/summaries* of extracted content in companion procedure docs (cheat sheets, pipelines) — they drift silently because they don't match section-name cross-ref greps.
