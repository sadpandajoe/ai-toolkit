# Cross-Cutting Principles

Most corrections belong in one existing rule file — `rules/gates.md` for a
gate wording problem, `rules/testing.md` for a test-runner mistake, and so
on. This file is the destination only for the remainder: a principle that
recurs across multiple workflows or skills and doesn't map cleanly to any
single existing rule file. If one clear owning file exists, the correction
belongs there instead, not here.

## Promotion path

`skills/reflection` clusters `observation` and `gate` events looking for
recurring corrections. Its step 4 ("If no clear owning rule or skill can be
identified...") is what feeds this file: when a cluster is real (not a
one-off) and genuinely crosses more than one skill's or rule's scope,
reflection proposes a new entry here rather than forcing it into an
unrelated file or dropping it. As with every other reflection output, this
is a proposal under `.ai-toolkit/proposals/<date>/`, not a silent edit —
`rules/rule-maintenance.md`'s Scope section governs: propose, get human
approval, then apply.

## Current principles

None promoted yet. This file exists as the wired destination for the first
qualifying cluster; an empty list here means no cross-cutting pattern has
recurred enough to earn a spot yet, not that the mechanism is unused.
