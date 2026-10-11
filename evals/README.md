# Evals

Tests protect invariants and deterministic state transitions; evals protect
model judgment. Neither exists to preserve an architecture the toolkit no
longer wants.

Each family is a JSONL file of cases with `id`, `mode`, `input`, `expected`,
and `source` (`plan`, `migration`, or `observation` when it came from the
reflection queue).

| Family | Protects |
|---|---|
| `skill_routing/` | Natural-language request → workflow, remediation on or off |
| `complexity/` | TRIVIAL / STANDARD / COMPLEX, size, execution shape, hard overrides |
| `gates/` | RETRY versus ESCALATE, evidence rule, safety gates, delta-review policy |
| `planning/` | Single-phase versus decomposition, just-in-time phase plans, bounded validation |
| `workflows/` | End-to-end behavior on representative tasks, resume from the snapshot |

## Running

- `mode: deterministic` cases run in `tests/test_evals.py` through the
  toolkit's own code (`aitk route`, `aitk.project_state`), so they are part of
  `bin/aitk check`.
- `mode: judgment` cases run with `bin/aitk eval`, which calls a provider and
  costs money; they are not run in CI. A case whose `expected` names
  `covered_by` is skipped: a test already covers it.

```
bin/aitk eval --provider <claude|codex> [--family <family>]... [--case <id>]...
              [--model <family>]... [--effort low|medium|high|xhigh]
              [--grader-provider <claude|codex>] [--jobs N] [--output FILE] [--dry-run]
```

Each case is two calls through the `model-run` transport (`aitk/eval.py`):

1. **Answer.** The model under test plays the parent session. Its instruction
   channel carries the family's contracts (`FAMILY_CONTRACTS` in
   `aitk/eval.py`: `rules/universal.md` plus the files that own that family's
   decisions); the task is the case's `input` and the names of the `expected`
   keys, never their values. It answers one JSON object with those keys. The
   dispatch is read-only and has no reviewed tree, so it can never back a
   review gate.
2. **Grade.** [`grader.md`](grader.md) compares the answer with `expected`
   key by key and returns `Verdict: PASS` or `Verdict: FAIL` on its summary's
   first line, with one finding per mismatched key. The grader runs on the
   grading provider's `review` route model and effort; `--grader-provider`
   picks the provider, so two providers' runs can share one grader.

Without `--model`, planning cases run on the `planning` route's model and
effort, and every other family on the orchestrator model
(`policy.orchestrator` in `interfaces/model-routing.json`) at the standard
effort. `--model` (repeatable, a family from the provider's catalog) and
`--effort` replace those for the whole run; they change what the run measures,
never what a workflow dispatches. `--dry-run` lists the dispatches and the
contracts without calling a provider; run it first.

## Results

Each run appends a section to `evals/results/<date>-<provider>.md`: the
command, the toolkit commit, the grader, then per setting (model and effort)
the passes, failures, errors and ungraded answers, the pass rate and the
API-equivalent cost of the answers and of the grading (the provider's own
figure, else its reported tokens priced by `aitk/pricing.py`), a table per
family and per case, and the misses with the grader's findings. `ERROR` means
no answer (outage, refusal or invalid result); `UNGRADED` means the grader
returned no verdict. A run that graded nothing exits 3. Phase 6 decisions are
recorded under the run they rest on.

Track the false-COMPLEX rate (wasted premium calls) and the false-STANDARD rate
(rabbit holes) from these results. Add a case whenever an observation shows a
misroute, a reclassification, or a repeated gate failure.

## Measurements

Each needs a logged-in provider CLI and spends money, and the replay set
(`evals/replay/`) needs its scored tasks first. Record every outcome in that
day's `evals/results/` file.

- **Provider comparison.** `bin/aitk eval --provider claude --model opus
  --model fable --model sonnet --grader-provider claude` and `bin/aitk eval
  --provider codex --model sol --model astra --grader-provider claude`, then
  the replay set on each provider. One grader keeps the two files comparable.
- **Planning route.** `bin/aitk eval --provider codex --family planning
  --model sol --model astra`, with the replay set's COMPLEX tasks. Settles
  whether Codex `planning` stays on sol or moves to astra.
- **Orchestrator.** `bin/aitk eval --provider claude --family complexity
  --family gates --family skill_routing --family workflows --model sonnet`,
  then the same with `--model opus --effort medium`; and an A/B on the replay
  set: Opus 5.5 at medium as the orchestrator, and one strong model end to end
  on COMPLEX tasks against plan, validate, implement. Settles whether the
  orchestrators stay Sonnet 5.5 and GPT-6.1 Sol.
- **Effort.** For each route, from the starting points (operations low or
  medium; Sonnet implementation medium; Opus review and RCA medium against
  high; Fable planning and deep routes high), rerun the matching eval with
  `--model <family> --effort <level>` one level at a time downward, and the
  replay set at each level; each run appends its own section with correctness
  and cost. Settles each route's pinned effort: the lowest level that keeps
  every case and replay task the highest level passed. A route's `effort`
  lives in `interfaces/model-routing.json`, and `aitk/routing_manifest.py`'s
  expected route table pins it as well.
- **A cheap `operations` model.** In a scratch branch, add Haiku 5.5 or GPT-6
  Luna to the provider's model catalog and point `operations` at it at low,
  then medium; run the replay tasks that use `operations` and compare their
  correctness with the current model. `operations` moves only if correctness
  holds; judgment routes never do.
- **Rule yield.** `bin/aitk rule-yield [--runs N]` lists the rule files no
  observation named (`bin/aitk observe --rule <rules/file.md>`) over the last
  20 workflow runs; `reflect` reviews them as deletion candidates.
