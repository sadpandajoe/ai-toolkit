# Specialist Handoff

Only the parent reads this file. A worker receives its own contract, the
boundary's `contracts` list in `interfaces/model-routing.json` or a native
agent's body, and never this one.

The spawn prompt is the only channel to a worker or specialist. It carries the
complete bounded contract inline; it never carries the parent transcript, and
the worker never carries its own transcript back.

## Critic profile

Critics are the independent reviewer, the second-family lane, the finding
verifier, the deep lenses, the plan validator and the adversarial lens. A
critic is worth running because it sees the work cold, so its prompt carries
only:

- the artifact under review: the diff and changed files with the recorded
  base, or the plan;
- the preflight result, the classifier's risk flags and the acceptance
  criteria;
- the route's restrictions.

Critics stay cold. The prompt never carries:

- the transcript or the implementer's notes;
- other lanes' findings;
- "look for X" steering;
- `PROJECT.md`, `PLAN.md` or `.ai-toolkit/` content.

**Do not steer the reviewer.** The prompt supplies diff facts, risk flags, and
posture; never a finding shape.

Two named exceptions see earlier work: the delta reviewer receives the accepted
findings and the fix diff, and an informed retry or revision receives the
evidence of the attempt that failed.

## Builder and investigator profile

Builders and investigators are the implementer, the tester, the debugger, the
planner and the RCA producer. They work from what the parent already knows, so
give them:

- the goal and why it matters, with the routing snapshot line (workflow,
  complexity, size, shape, current phase);
- the accepted artifact: the plan slice, the RCA, or the brief;
- what was tried, with evidence;
- what was ruled out;
- known traps;
- scope, the route's restrictions (routed workers never commit), the exit
  criteria and the exact acceptance command the parent will run.

Inline excerpts rather than paths a sandbox cannot read.

## Output

Routed workers (`model-run`) return the runner's JSON result and put their
content in `status`, `summary`, `findings`, and `verification`. Native agents
return this block:

```markdown
## Handoff: <worker or specialist>
Status: completed | blocked | failed
Result: <what changed or what you found>
Evidence: <commands run and results, or "none run">
Files: <changed or inspected>
Findings: <severity-tagged list, or none>
Residual risk: <or none>
Next: <what the parent should do>
```

No raw logs or full diffs: quote the lines that carry the evidence and give
paths for the rest, so the parent never reads a worker's logs or transcript.
Nobody can answer a question while a worker runs, so finish everything the
contract covers, and return `blocked` only for a fact or decision you cannot
get yourself, naming it. The parent writes durable state; the worker never
edits `PROJECT.md` or `PLAN.md`.

## Consuming a specialist's findings

Independent reviewers and validators are critics, not authorities. Before
changing code, validate each finding against the current repo and diff. Track
accepted versus rejected, and give every rejection a one-line evidence-based
reason. Accepted findings per pass is the reviewer-yield metric that decides
whether a lane keeps running.
