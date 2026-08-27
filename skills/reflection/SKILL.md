---
name: reflection
description: Use when reviewing recorded gate-escalation history to find rules that keep failing the same way and need strengthening — natural-language requests like "review gate escalations", "what rules keep drifting", "check telemetry for stale rules", or periodic rule-maintenance sweeps. Do NOT use for reading metrics for pass-rate/round-count/worker-usage reporting with no rule-maintenance angle (the `metrics` workflow), for structurally auditing or editing skills/rules/interfaces with no telemetry basis (skills/agent-setup-maintainer), or for handling a single live gate failure inside a running workflow (the calling workflow's own `rules/gates.md` handling, not this skill).
---

# Reflection

## Before Starting

Read `rules/rule-maintenance.md` first — its Drift-catching mechanism
section defines the signal this skill acts on (gate escalation history) and
its "When a rule is violated" section defines what to do once a stale rule
is found. This skill is the review pass that walks from one to the other; it
does not redefine either.

## Scope

**In scope:** reading recorded `gate` events from `.ai-toolkit/metrics.jsonl`
(emitted per `rules/gates.md`'s Telemetry section), finding gates whose
escalation rate for the *same* reason is high across many runs, mapping each
back to the rule backing that checkpoint, and proposing a strengthened rule
per `rule-maintenance.md`'s "When a rule is violated" steps.

**Out of scope:** applying the proposed rule change without the user's
review (`rule-maintenance.md`'s Scope section: rule changes are proposed
during the summary, not applied silently); aggregate metrics reporting with
no rule-maintenance angle (`skills/workflows/references/metrics.md` already
computes the same escalation-rate figure for general reporting — this skill
reuses that computation, not a second one); and any live gate decision
inside a running workflow, which stays that workflow's own responsibility.

## Steps

1. Read `.ai-toolkit/metrics.jsonl`. If it does not exist or has no `gate`
   events, stop and report there is nothing to review yet — this is the
   expected state until a live goal-skill run populates the file.
2. Group `gate` events by `gate` name. Within each group, further group by
   `reason` where recorded, and compute the `ESCALATE` rate per
   `(gate, reason)` pair — mirrors `metrics.md`'s "Gate retry/escalation
   rate" computation; do not reimplement a different formula.
3. Flag a `(gate, reason)` pair as drifting when `ESCALATE` recurs for that
   same reason across multiple distinct runs — a single run's repeat count
   climbing during one workflow attempt is expected iteration, not drift;
   the signal is the *same* reason resurfacing across separate runs.
4. For each flagged pair, identify the rule file backing that checkpoint —
   the calling skill's own `Before Starting` citation of `rules/gates.md`
   (or a more specific rule it names for that checkpoint) is the usual
   source. If no clear owning rule can be identified, report the raw
   finding instead of guessing.
5. Apply `rule-maintenance.md`'s "When a rule is violated" steps as a
   proposal, not an edit: draft the strengthened language (NEVER list, a
   concrete example of the failure pattern, or a note to load the rule
   earlier), but do not write it to the rule file — present it in the
   summary for the user to accept, adjust, or decline.

## Output

```markdown
## Reflection Summary
Gates reviewed: N
Drifting: [(gate, reason) pairs flagged, or "none"]
Proposed rule changes: [file -> proposed strengthening, or "none"]
```

## Notes

- This skill only ever proposes; it never edits a rule file itself — that
  stays a user decision per `rule-maintenance.md`'s Scope section.
- Nothing in this repo has emitted a live `gate` event yet (no goal skill
  has run end-to-end here), so step 1's early stop is the expected outcome
  until that changes — this skill's own Steps section is exercised for real
  only once real telemetry exists.
