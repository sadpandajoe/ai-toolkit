# Architecture

AI Toolkit separates stable workflow behavior from provider syntax.

## Layers

1. `rules/` contains short cross-workflow constraints.
2. `skills/` contains canonical Agent Skills and lazy references. `skills/workflows/` is the public daily-workflow router.
3. `interfaces/workflows.json` and the optional extension manifests declare
   workflow identity, owner skill, routing, rule imports, and execution class.
   `interfaces/contracts.json` v2 declares the phase graph, authorization,
   effects, idempotency, verification, reporting, and recovery behavior.
   `interfaces/skills.json`, `providers.json`, `guidance.json`, and
   `support.json` make public discovery, provider capabilities, shared
   always-on guidance, and the release matrix explicit.
4. `commands/` is generated Claude compatibility output. It imports rules and one canonical workflow reference; it contains no procedure.
5. `.codex-plugin/`, `skills/*/agents/openai.yaml`, `hooks/hooks.json`, and `config/AGENTS.md` form the Codex adapter.
6. `aitk/` and `bin/aitk` build, route, validate, transact installation, and
   serialize durable workflow checkpoints.

Optional extensions repeat the same pattern below `extensions/<name>/`: a manifest, canonical Agent Skill, generated compatibility commands, and any extension-specific rules. `--with-pgm` opts the bundled PGM extension into build, routing, and installation.

The version 0.1.0 Codex plugin packages the core `skills/` tree. PGM remains an
explicitly source-linked extension until plugin distribution supports its
separate skill root; `interfaces/support.json` makes that distribution boundary
machine-readable.

## Source-of-truth flow

```text
workflow manifest + v2 contract + canonical skill reference
                 │
       ┌─────────┴──────────┐
       │                    │
 bin/aitk build      checkpoint runtime
       │            (phase/effect ledger)
       │                    │
generated deprecated  PROJECT.md machine block
Claude alias
```

Provider adapters may translate invocation syntax, tool names, planning controls, scheduling, and independent-review capabilities. They may not weaken authorization boundaries, protected state, stop conditions, verification labels, or reporting contracts.

## State and recovery

Long-running workflows write human state plus one canonical
`aitk-checkpoint:v1` JSON block in `PROJECT.md`. `bin/aitk checkpoint` owns its
serialization, legal phase transitions, generation counter, and pending/applied
effect records. A stable operation ID is reserved before an effect and applied
only after execution or reconciliation. Semantic contract changes invalidate
old checkpoints through a canonical contract digest. Effect keys are categories,
not one-shot slots: repeated pushes, posts, and review rounds append distinct
records keyed by their stable operation IDs.

Focused manifests such as `PLAN.md`, `WATCH.md`, or `CI_FIX.md` can supplement
that checkpoint. All local workflow-state files are ignored by git and blocked
by the safety hook if staged. Resume uses durable files, never chat history.

## Install ownership

Source-linked installation is a transaction recorded in mode-0600
`~/.ai-toolkit/install-state.json`. The inventory is derived from the manifests
and public skill classification. Guidance is owned only inside delimiters;
links are owned by exact target/source records. Install/upgrade, uninstall, and
one-level rollback validate every ledger path before mutation, preserve user
conflicts, and restore exact bytes/modes/links on pre-commit failure. A moved
checkout is an explicit upgrade whose prior root remains recoverable.

Internal skills are packaged for resolver use but are not linked as standalone
Agent Skills. Generated `commands/` files are deprecated Claude aliases and
have no lifecycle or behavior authority.

## Adding a workflow

1. Add `skills/workflows/references/<name>.md`.
2. Register the name, summary, arguments, rules, and routing triggers in `interfaces/workflows.json`.
3. Add a total v2 entry to `interfaces/contracts.json`; use the canonical
   durable runtime rule and runtime-contract section when execution is durable.
4. Classify any new skill in `interfaces/skills.json`.
5. Run `bin/aitk build` (or `--with-pgm` for the bundled extension).
6. Add positive and negative routing, semantic, recovery, and adapter cases,
   then run `bin/aitk check`.

Do not add workflow logic to `commands/`, provider config, hooks, or the manifest.

For an optional extension, use the matching `extensions/<name>/interfaces/workflows.json` and `extensions/<name>/skills/<name>/references/` locations, then validate its generated aliases with the same conformance gate.
