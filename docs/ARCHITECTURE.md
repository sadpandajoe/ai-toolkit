# Architecture

AI Toolkit separates stable workflow behavior from provider syntax, and puts
the control plane in the cheapest capable model.

## Layers

1. `rules/` holds short cross-workflow constraints: durable state, gates and
   the retry budget, complexity and size classification, model roles, the
   specialist handoff contract.
2. `skills/` holds canonical Agent Skills and lazy references.
   `skills/workflows/` is the public router; its references are the goal
   workflows (thin state machines the parent runs inline). Domain skills
   (`planning`, `review`, `debug`, `testing`, `qa`, `feedback`, ...) hold
   reusable knowledge loaded at phase entry. `skills/verification-loop/` is
   the shared verify, fix, recheck loop every goal workflow chains.
3. `agents/` holds the worker roster. `agents/claude/*.md` and
   `agents/codex/*.toml` are native subagent definitions the installer links
   into the user's provider directories: planner (Opus, read-only),
   implementer, debugger, tester (Sonnet), and a same-provider reviewer
   fallback. `agents/specialists/*.md` are provider-neutral contracts
   (reviewer, RCA, plan validator) the route runner inlines into
   cross-provider specialists.
4. `interfaces/` makes everything machine-checkable: workflow identity and
   triggers, v2 durable contracts, skill classification, provider capability
   bindings, model routing (catalog, routes, dispatch boundaries, lens floors),
   always-on guidance, and the support matrix.
5. `aitk/` and `bin/aitk` build, route, validate, install transactionally,
   serialize checkpoints, and own the `PROJECT.md` routing snapshot.

## Control Plane

The parent session runs on the workhorse family named in
`interfaces/model-routing.json` (`policy.orchestrator`). A goal workflow reads
the routing snapshot, evaluates the current gate, runs the next bounded
capability, records the handoff, and repeats until every required gate is
`PASS`. Only `USER_DECISION`, `BLOCKED`, and the hard safety gates in
`interfaces/contracts.json` reach the user.

Classification has two orthogonal axes plus a derived shape:

- **Complexity** (`TRIVIAL` / `STANDARD` / `COMPLEX`) chooses the reasoning
  tier. Hard signals (migrations, auth, public contracts, concurrency, caching,
  cross-service, compatibility, new architecture) force `COMPLEX`.
- **Size** (`S` / `M` / `L` / `XL`) estimates implementation surface.
- **Execution shape** (`SINGLE_PHASE` / `BATCHED` / `MULTI_PHASE`) is derived
  by `aitk.project_state.derive_execution_shape` from size and a phaseability
  judgement; L must be assessed, XL decomposes by default unless mechanical.

`aitk project-state` persists the snapshot in a delimited block in
`PROJECT.md`, records gate outcomes, and enforces the attempt budget: a unit
gets one attempt and one informed retry per owner, and the runtime turns a
third `RETRY` into `ESCALATE`. An escalation climbs a bounded per-unit ladder
(three steps, then `USER_DECISION`) and resets the budget for the next owner;
editorial retries, `USER_DECISION`, and `BLOCKED` are recorded without being
charged; `RECLASSIFY` resets the counters. Verification gates carry a strength
(`STRONG` / `PARTIAL` / `WEAK`), and only `STRONG` authorizes an auto-push.

## Isolation and Routing

Fresh workers are the phase boundary. The parent keeps only intent, the active
skill, the snapshot, gate results, and short handoffs; large logs, diffs, and
implementation detail live in workers that return the compact handoff in
`rules/specialist-handoff.md`. No workflow depends on a manual context clear.

Same-provider workers are native subagents. Independent review, RCA
validation, and plan validation prefer the other provider and cross the
source-linked transport: skills name stable routes at inventoried markers,
`bin/aitk model-route` resolves selector, effort, and permissions, and
`bin/aitk model-run` inlines the boundary's validated contract closure, pins one
selector, forbids fallback, and validates the result envelope. Codex targets run
from a sanitized temporary project root with a scoped `--add-dir` and no user
config, hooks, MCP servers, or project documents. Provider result formats do
not attest the internal serving model, so backend substitution stays outside
the toolkit's evidence boundary.

Review is one independent lane by default, validated by the parent before any
fix, with one delta pass after substantive remediation and at most two
`deep-review` lenses (adversarial, deep quality, architecture) on classifier
flags. A `[major]` only one lane raised is confirmed by a fresh verifier on the
other model family before it blocks, and a security-sensitive, `--deep`, or
adversarial review is `BLOCKED (degraded)` rather than downgraded when the
other provider is unreachable. Plan validation is one worker returning `APPROVE / CHANGES_REQUIRED /
REPLAN`; the RCA gate is an evidence checklist the parent grades for STANDARD
bugs and a specialist grades for COMPLEX or uncertain ones.

## Source-of-truth flow

```text
workflow manifest + v2 contract + canonical skill reference
                 │
       ┌─────────┴──────────┐
       │                    │
 routing/validation   snapshot + checkpoint runtime
                            │
                   PROJECT.md machine blocks
```

## State and recovery

Long-running workflows write human state plus two machine blocks in
`PROJECT.md`: the `aitk-project-state:v2` routing snapshot and the
`aitk-checkpoint:v1` phase and effect record. `bin/aitk checkpoint` owns phase
transitions, the generation counter, and pending/applied effect records with
stable operation IDs. Focused manifests (`PLAN.md`, `WATCH.md`, `CI_FIX.md`,
`CHERRY_PICK.md`) supplement it. All local workflow-state files are ignored by
git and blocked by the safety hook. Resume uses durable files, never chat.

## Learning loop

High-signal events (user corrections, misroutes, reclassifications, repeated
gate failures, specialist invalidations, repeated workarounds, low-yield review
lanes) append to `.ai-toolkit/observations.jsonl`. `reflect` clusters them,
proposes rule or skill changes for human approval, and writes eval candidates
under `evals/`. Tests protect invariants and deterministic transitions; evals
protect model judgment.

## Install ownership

Source-linked installation is a transaction recorded in mode-0600
`~/.ai-toolkit/install-state.json`. The inventory is derived from the
manifests, the public skill classification, and the agent roster. Guidance is
owned only inside delimiters; links are owned by exact target/source records.
Install, uninstall, and one-level rollback validate every ledger path before
mutation and preserve user conflicts.

## Adding a workflow

1. Add `skills/workflows/references/<name>.md` in the goal-loop shape used by
   `fix-bug.md` and `create-feature.md`.
2. Register it in `interfaces/workflows.json` (rules, triggers, class) and add a
   total v2 entry to `interfaces/contracts.json`.
3. Mark every dispatch sentence with an inventoried route marker and declare the
   boundary (routes, contracts, lens menu when it fans out) in
   `interfaces/model-routing.json`; pin its route ceiling in
   `aitk/routing_manifest.py`.
4. Add routing, classification, and gate eval cases under `evals/`.
5. Run `bin/aitk check`.

Do not add workflow logic to provider config, hooks, or the manifest.
