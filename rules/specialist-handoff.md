# Specialist Handoff

The spawn prompt is the only guaranteed channel to a worker or specialist. It
carries the complete bounded contract inline; it never carries the parent
transcript, and the worker never carries its own transcript back.

## Into a worker (maximum contract)

- **Goal and phase**: one sentence each, plus the routing snapshot line
  (workflow, complexity, size, shape, current phase).
- **Scope**: files or areas in scope, and what is explicitly out of scope.
- **Artifact pointer or excerpt**: the accepted plan slice, RCA, or diff the
  worker acts on. Inline excerpts rather than paths a sandbox cannot read.
- **Constraints**: the route's restrictions, whether commits are allowed
  (routed workers: never), and any invariant the change must preserve.
- **Exit criteria**: the observable conditions that mean done, and the exact
  acceptance command the parent will run.
- **Output schema**: the handoff block below, or the structured result the
  route runner enforces.

Do not include: prior review rounds, other lanes' findings (a cold reviewer
must not see them), conversation history, or "look for X" steering that
pre-decides the finding.

## Out of a worker (compact handoff)

Native agents return this block. Routed workers (`model-run`) return the
runner's JSON result instead and put the same content in `status`, `summary`,
`findings`, and `verification`.

```markdown
## Handoff: <worker or specialist>
Status: completed | blocked | failed
Result: <what changed or what you found, briefly>
Evidence: <commands run and results, or "none run">
Files: <changed or inspected>
Findings: <severity-tagged list, or none>
Residual risk: <one line, or none>
Next: <what the parent should do>
```

Quote the few lines that carry the evidence and give paths for the rest: the
parent keeps its context small and never reads a worker's logs, full diffs, or
transcript. Nobody can answer a question while a worker runs, so finish
everything the contract covers, and return `blocked` only for a fact or
decision you cannot get yourself, naming it. The parent writes durable state;
the worker never edits `PROJECT.md` or `PLAN.md`.

## Consuming a specialist's findings

Independent reviewers and validators are critics, not authorities. Before
changing code, validate each finding against the current repo and diff. Track
accepted versus rejected, and give every rejection a one-line evidence-based
reason. Accepted findings per pass is the reviewer-yield metric that decides
whether a lane keeps running.
