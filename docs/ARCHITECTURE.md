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
   into the user's provider directories: planner (Fable, read-only),
   implementer, debugger and tester (Sonnet). There is no native reviewer: the
   second-family review and its single-family fallback run through
   `bin/aitk model-run`. Each provider has a workhorse family and a deep family
   (Sonnet and Opus with Fable; Sol with Astra); deep routes run only on the
   deep family. `agents/specialists/*.md` are provider-neutral contracts
   (planner, reviewer, RCA, plan validator, finding verifier) the route runner
   inlines into cross-provider specialists.
4. `interfaces/` declares workflow identity and triggers, each workflow's
   effect and authorization, skill classification, provider capability
   bindings, model routing (catalog, routes, dispatch boundaries, lens floors),
   and always-on guidance.
5. `aitk/` and `bin/aitk` build, route, install transactionally, and own the
   `PROJECT.md` state block.

Context model: rules are short always-on constraints and routing hints; skills
own workflow context and load only at phase entry, and their descriptions are
classifiers with explicit use and do-not-use boundaries; provider adapters
translate capabilities and never own behavior. Work moves in small verified
steps, narrowest approach first (YAGNI): a working solution, then
optimization.

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
gets one attempt and one informed retry per owner, and the runtime turns the
second `RETRY` into `ESCALATE` (or the first, when it repeats a failure that
already exhausted a previous owner). An escalation climbs a bounded per-unit ladder
(three steps, then `USER_DECISION`) and resets the budget for the next owner;
editorial retries, `USER_DECISION`, and `BLOCKED` are recorded without being
charged; `RECLASSIFY` resets the counters. Verification gates carry a strength
(`STRONG` / `PARTIAL` / `WEAK`), and only `STRONG` authorizes an auto-push.
`STRONG` is backed by a run record: `aitk verify --run` runs the command and
records its exit code, output tail and tree on the gate, and a review PASS
carries the reviewer envelopes' digests and the reviewed tree (`gate --result`).
A PASS without its record does not count for `aitk deliver` or the PR hook.

## Isolation and Routing

Fresh workers are the phase boundary. The parent keeps only intent, the active
skill, the snapshot, gate results, and short handoffs; large logs, diffs, and
implementation detail live in workers that return the compact handoff in
`rules/specialist-handoff.md`. No workflow depends on a manual context clear;
auto-compaction is only a safety net. A worker is reused only inside the same
bounded phase, when re-discovery would cost more than the resume; across
phases it starts fresh. Provider task lists mirror state and never replace the
files.

Same-provider workers are native subagents. Independent review, RCA
validation, and plan validation prefer the other provider and cross the
source-linked transport: skills name stable routes at inventoried markers,
`bin/aitk model-route` resolves selector, effort, and permissions, and
`bin/aitk model-run` passes the boundary's explicit contract list through the
provider's instruction channel (Claude `--append-system-prompt-file`, Codex
`developer_instructions`) with the task alone in the user message, pins one
selector and effort, forbids fallback, and validates the result against the
lane's own schema. Codex targets run with an isolated `CODEX_HOME` that holds
only the auth file, from an empty temporary project root with a scoped
`--add-dir`, and with no user config, hooks, MCP servers, or project documents.
The one variant is the Phase 6 `--experiment reviewer-runs-test` measurement:
the independent reviewer runs from a disposable copy of its worktree and may
run allowlisted test commands there ([evals/README.md](../evals/README.md)).
A provider refusal is recorded as `refused`, apart from an outage; a refused
adversarial lens reroutes once to the other provider, recorded in the result. Provider result formats do
not attest the internal serving model, so backend substitution stays outside
the toolkit's evidence boundary.

Review policy is code: `bin/aitk review plan` computes which lanes run, by
tier, flags and yield thresholds (`aitk/review_plan.py`), and `review merge`
dedupes their findings and lists the majors to verify. The parent's judgment
(validating findings, what counts as substantive, locking tests, disputes)
lives in `skills/review/references/local-review.md`, and the grading
calibration every review lane receives in `rules/code-review.md`.

`bin/aitk lane-yield` applies the yield thresholds to each lane's recent runs
in the metrics file and queues a `low-yield-lane` observation per demotion;
`bin/aitk build` renders this table from the same constants:

<!-- aitk-generated:lane-yield -->
<!-- Generated by `bin/aitk build`; do not edit. -->
| Lane | Window (runs) | Demoted when | Consequence |
|---|---|---|---|
| `adversarial`, `deep-quality`, `architecture` | 5 | no accepted finding, or fewer than 1 accepted per 4 raised | opt-in only: run on an explicit ask until reflect reviews it; record the classifier flag as deferred (low yield) |
| `second-family` | 10 | no accepted finding the other lanes missed, and none refuted | COMPLEX only: drop the CORE trigger |
| `verify-major` | 10 | CONFIRMED on fewer than 3 in 10 verified majors | single-source majors from the raising lane default to [minor]; write a low-yield-lane observation for that lane |
| `delta` | 10 | no not-fixed and no introduced finding | delta pass runs only after a [major] fix |

`independent` is never demoted.
<!-- /aitk-generated:lane-yield -->

A boundary's contract list is the worker's whole closure, so it carries only
what that lane grades with. Posting rules stay out of the batch reviewer's
list: a review route is read-only and network-less, so the worker could
neither fetch nor post, and an inlined posting contract would only invite it
to try. The main thread fetches each PR's payload, posts, and records the
batch's code-judo suppression itself. Code-judo runs only at its own
`review.code-judo` boundary, which accepts `deep-review` alone and fails
closed on any other route; batch review never fans it out, because its
proposals have no slot in the per-PR result and the deep route is too costly
to run across a batch.

A watch keeps the same isolation: a fix runs in an `implementation` worker
that returns a compact handoff, classification and diagnosis stay with the
parent or an `rca`/`deep-rca` worker, and check JSON, CI logs, diffs, and
review rounds stay out of the parent, so an idle iteration costs only a
heartbeat. `WATCH.md` and the state block are current after every iteration,
so a session that ends for any reason resumes from them through `start`.

## Source-of-truth flow

```text
workflow manifest + contract + canonical skill reference
                 │
       ┌─────────┴──────────┐
       │                    │
    routing          bin/aitk project-state
                            │
                   PROJECT.md state block
```

## State and recovery

Long-running workflows write human state plus one machine block in
`PROJECT.md`: the `aitk-project-state:v2` state block, which only
`bin/aitk project-state` writes. It holds the classification, the current
phase and gate, the attempt budget and escalation ladder, the per-gate record
with its evidence (`gates`), the phase table and the operation log. Focused
manifests (`PLAN.md`, `WATCH.md`, `CI_FIX.md`, `CHERRY_PICK.md`) supplement it.
All local workflow-state files are ignored by git and blocked by the safety
hook. Resume uses durable files, never chat: `start` reads the state block,
re-runs classification only when the recorded complexity predates the current
tiers, and continues at the recorded gate. Human-readable status follows the
block, with ISO timestamps. A workflow adds a summary template under
`skills/reporting/templates/` only when it needs structured domain output.

Effects read the gates from the same block. `bin/aitk deliver` and the review
gate hook apply one check (`gate_blockers`): verification and review must be
`PASS` in the current phase, each backed by its evidence. The record is
scoped: each gate entry carries the phase it was recorded in and the latest
outcome per reasoning unit, `advance` clears `verification` and `review`, and
a `PASS` recorded in another phase or alongside an open `RETRY` on another
unit does not count. A repeated reply or rerun is caught by
`project-state op --check`. Every write takes one lock per state file, so a
gate record and an operation record cannot overwrite each other. A workflow
without a snapshot has no gate history, so every workflow that records a gate
runs `project-state init` first, including standalone `review-plan` and
`fix-ci`.

## Learning loop

High-signal events (user corrections, misroutes, reclassifications, repeated
gate failures, specialist invalidations, repeated workarounds, low-yield review
lanes) append to `.ai-toolkit/observations.jsonl`. `reflect` clusters them,
proposes rule or skill changes for human approval, and writes eval candidates
under `evals/`. Tests protect invariants and deterministic transitions; evals
protect model judgment: `bin/aitk eval` runs the judgment cases on one
provider and grades them (`evals/README.md`), and `bin/aitk rule-yield`
lists the rule files no observation named recently.

## Cost and metrics data

`bin/aitk cost [period]` (`aitk/cost.py`) reads Claude Code session JSONL
files under `~/.claude/projects/`, so cost data is Claude-only: it reads no
Codex or other provider telemetry and never infers their usage. Costs are API-equivalent estimates from
`aitk/pricing.py`, not bills, and unpriced beats guessed. A promotional price
is chosen from the record's timezone-aware timestamp, so a missing, invalid or
timezone-free timestamp leaves that record unpriced, as does an unknown model
family; token and message counts stay visible either way.

Workflow metrics are separate, provider-neutral events in
`.ai-toolkit/metrics.jsonl` (`bin/aitk metrics`), read from the legacy
`.claude/metrics.jsonl` only when the canonical file does not exist.

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
2. Register it in `interfaces/workflows.json` (rules, triggers, class) and add
   its entry (effect, authorization, state, verification strength) to
   `interfaces/contracts.json`.
3. Put an `aitk-model-route:` marker before each worker dispatch and declare the
   boundary (routes, contracts, lens menu when it fans out) in
   `interfaces/model-routing.json`, which is the whole route table.
4. Add routing, classification, and gate eval cases under `evals/`.
5. Run `bin/aitk check`.

A workflow reference keeps its visible gates, path rules, workflow-specific
complexity signals and final stop conditions, puts a short happy path before
any dense routing table, and names the owner, route and load or handoff
condition at each step. Keep ownership and routing in one section so they
cannot drift; import only short rules in the header, never skills, long
references, templates or examples; and keep an end-to-end flow in its workflow
rather than in a domain skill whose boundary disclaims it. When auditing a
workflow, compare it with `create-feature` before inventing a new structure.

Do not add workflow logic to provider config, hooks, or the manifest.
