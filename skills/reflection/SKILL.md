---
name: reflection
description: Use when reviewing recorded gate-escalation or correction history to find rules, skills, or routing that keep failing the same way and need strengthening — natural-language requests like "review gate escalations", "what rules keep drifting", "check telemetry for stale rules", "review recent corrections", or periodic rule-maintenance sweeps. Do NOT use for reading metrics for pass-rate/round-count/worker-usage reporting with no rule-maintenance angle (the `metrics` workflow), for structurally auditing or editing skills/rules/interfaces with no telemetry basis (skills/agent-setup-maintainer), or for handling a single live gate failure inside a running workflow (the calling workflow's own `rules/gates.md` handling, not this skill).
---

# Reflection

## Before Starting

Read `rules/rule-maintenance.md` first — its Drift-catching mechanism
section defines the signal this skill acts on (gate escalation history) and
its "When a rule is violated" section defines what to do once a stale rule
is found. This skill is the review pass that walks from one to the other; it
does not redefine either.

## Scope

**In scope:** reading recorded `gate` and `observation` events from
`.ai-toolkit/metrics.jsonl` (per `rules/gates.md`'s Telemetry section and
`skills/metrics-emit`'s `observation` event), finding gates whose escalation
rate for the *same* reason is high across many runs and `observation`
clusters that recur for the same skill/kind, mapping each back to the rule
or skill backing it, writing a proposal per `rule-maintenance.md`'s "When a
rule is violated"/"When a new pattern emerges" steps, and — for an ACTIONED
`skill-misroute` or `gate-repeat` correction — writing a candidate eval
fixture so the same correction becomes a structural regression check.

**Out of scope:** applying a proposed change without the user's review
(`rule-maintenance.md`'s Scope section: changes are proposed, not applied
silently — this now includes skill changes, not just rules); aggregate
metrics reporting with no rule-maintenance angle
(`skills/workflows/references/metrics.md` already computes the same
escalation-rate figure for general reporting — this skill reuses that
computation, not a second one); and any live gate decision inside a running
workflow, which stays that workflow's own responsibility.

## Steps

1. Read `.ai-toolkit/metrics.jsonl`. If it does not exist or has neither
   `gate` nor `observation` events, stop and report there is nothing to
   review yet — this is the expected state until a live goal-skill run
   populates the file.
2. **Gate clustering.** Group `gate` events by `gate` name, then by `reason`
   where recorded, and compute the `ESCALATE` rate per `(gate, reason)` pair
   — mirrors `metrics.md`'s "Gate retry/escalation rate" computation; do not
   reimplement a different formula. Flag a pair as drifting when `ESCALATE`
   recurs for that same reason across multiple distinct runs — a single
   run's repeat count climbing during one workflow attempt is expected
   iteration, not drift; the signal is the *same* reason resurfacing across
   separate runs.
3. **Observation clustering.** Group `observation` events with `status: OPEN`
   by `skill`, then by `kind`. Flag a `(skill, kind)` cluster once it has 2
   or more members — a single observation is a one-off; a cluster is a
   pattern.
4. For each flagged gate pair, identify the rule file backing that
   checkpoint — the calling skill's own `Before Starting` citation of
   `rules/gates.md` (or a more specific rule it names for that checkpoint)
   is the usual source. For each flagged observation cluster, read the
   `skill`/`issue`/`suggested_change` fields across its members to judge
   what's actually recurring. If a cluster genuinely spans more than one
   skill or rule's scope and no single existing file owns it, its
   destination is `rules/cross-cutting.md`, not a guess at the closest
   existing file — treat it like any other flagged cluster in step 6 (or
   step 5, if it also trips an escalation trigger), just with
   `rules/cross-cutting.md` as the target file in the proposal. Only report
   the raw finding without a target if even that file's promotion criteria
   don't fit.
5. **Escalation triggers — ask immediately instead of writing a silent
   proposal** when a flagged observation cluster's fix would mean any of:
   creating a new skill, restructuring an existing skill (its steps,
   scope, or file layout — not just its wording), or conflicting with an
   existing rule or a still-open proposal. Surface these in the summary as
   a question, not a proposal file, and wait for the user's direction before
   writing anything. A cluster whose fix is a rule-language strengthening,
   a stale-rule update, or a skill wording/example tweak does not trigger
   this — it proceeds to step 6.
6. For everything else, apply `rule-maintenance.md`'s "When a rule is
   violated"/"When a new pattern emerges" steps as a proposal, not an edit:
   draft the strengthened or corrected language (NEVER list, a concrete
   example of the failure pattern, a note to load the rule earlier, or a
   skill wording fix). Write it to
   `.ai-toolkit/proposals/<date>/<gate-or-skill>-<kind>.md` (one file per
   flagged pair/cluster; `<date>` is the run date, `YYYY-MM-DD`) containing
   the evidence (which events, how many, what recurs) and the proposed
   change — do not write it to the rule/skill file itself. Present the same
   content in the summary for the user to accept, adjust, or decline.
7. For every `observation` cluster addressed in step 5 or step 6 (asked
   about or proposed), emit a follow-up `observation` event per
   `skills/metrics-emit` for each member: `status: ACTIONED` if the user
   accepted the change (or an escalation question got a real answer),
   `status: DECLINED` if they turned it down, with `ref` pointing back to
   the original event's timestamp. A cluster left unaddressed this run
   stays `OPEN` for the next reflection pass.
8. **Correction → eval.** For every observation just marked `ACTIONED` in
   step 7 whose `kind` is `skill-misroute` or `gate-repeat`, write a
   candidate fixture recording the correction as a regression check, so the
   same misroute or repeat gets caught structurally next time instead of
   waiting for another live correction:
   - `skill-misroute` → `evals/skill_routing/candidates/<slug>.json`,
     shaped like the family's live fixtures (`aitk/evals_skill_routing.py`):
     `{"name": "<slug>", "phrase": "<the request text that misrouted>",
     "expect_skill": "<the correct goal skill>"}`. Derive `phrase` from the
     observation's `issue` field and `expect_skill` from `suggested_change`.
   - `gate-repeat` → `evals/escalation/candidates/<slug>.json`: `{"name":
     "<slug>", "gate": "<gate name>", "reason": "<failure reason>",
     "skill": "<owning skill>"}`. This is deliberately partial — a live
     `gate-repeat` observation doesn't record where the repeat count stood,
     so it can't carry the `kind`/`previous_count`/`expect_state`/
     `expect_count` fields `aitk/evals_escalation.py`'s checker needs.
     Promoting this candidate into a live fixture means a human adds those
     four fields (see that checker's own docstring for what each means),
     same as any other promotion in this step.
   - `<slug>` is a short kebab-case name unique within the family's
     `candidates/` directory (e.g. the skill name plus a short discriminator).
     Writing under `candidates/`, not directly in the family directory, is
     deliberate: `aitk/evals.py`'s `load_fixtures` globs `*.json`
     non-recursively, so a candidate never runs as a live fixture (and never
     fails CI) until a human reviews it and moves it up a directory — this
     skill proposes fixtures, it does not promote them, same as every other
     change here.

## Output

```markdown
## Reflection Summary
Gates reviewed: N
Drifting gates: [(gate, reason) pairs flagged, or "none"]
Observation clusters: [(skill, kind) pairs flagged, or "none"]
Escalated for a decision: [clusters requiring new-skill/restructure/conflict judgment, or "none"]
Proposals written: [.ai-toolkit/proposals/<date>/... paths, or "none"]
Candidate fixtures written: [evals/<family>/candidates/... paths, or "none"]
```

## Notes

- This skill only ever proposes; it never edits a rule or skill file itself,
  and never promotes a candidate fixture into a family's live set — both
  stay a user decision per `rule-maintenance.md`'s Scope section.
- The new-skill/restructure/conflict escalation triggers exist because those
  three classes of change have a blast radius a silent proposal file
  undersells — a new skill changes routing for every future request, a
  restructure changes an existing skill's contract for every existing
  caller, and a conflict means two proposals or a proposal and an existing
  rule disagree and only the user can pick.
- Nothing in this repo has emitted a live `gate` or `observation` event yet
  (no goal skill has run end-to-end here), so step 1's early stop is the
  expected outcome until that changes — this skill's own Steps section is
  exercised for real only once real telemetry exists.
