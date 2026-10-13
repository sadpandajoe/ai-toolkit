# Memory Management

> **When**: Capturing workflow patterns, reviewing accumulated memories, pruning stale entries, extracting rules from experience, recording failures, or promoting learnings to global rules.
> **Produces**: Updated memory files, pruned index, draft rules, structured postmortems, or promoted rules.

## Effect Boundary

Effect: `local_mutation`.

## Route

Each subcommand runs its phase of the `reflection` skill
(`skills/reflection/SKILL.md`): none, `add`, `list` → add or list memories;
`review`, `prune` → review or prune memories; `propose-rule`, `promote
<filename>` → propose or promote a rule; `failure` → failure postmortem;
`observations` → review observations. Memories live in the `memory_store`
directory.
