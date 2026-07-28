---
tier: Heavy
---

# Code-Judo (Structural Restructuring Proposal)

A **generative** pass, not a findings pass. Where the deep-quality findings lens
*finds* structural problems, this pass *proposes* a concrete behavior-preserving
restructuring that makes the change dramatically simpler. The two lenses are
deliberately separate contracts: naming that sibling file here would pull its
severity-graded findings rules into this lane's inline closure.

Pinned to the `deep-review` route (see the review SKILL Invocation section) —
this is deliberately the deepest-reasoning tier because reframing an
architecture requires holding an alternative design in view. This pass runs iff
`classify-diff` reports `Code-judo lane: YES`; that file owns the trigger
predicate (see its *Code-judo* row and *Deep-tier escalation* rule) and this
lens never re-derives it. The lane is deliberately conservative because the
`deep-review` route is expensive — a merely refactor-*shaped* diff is advisory
there, not an auto-fire.

<!-- aitk-model-route:review.code-judo -->
Dispatch a single code-judo agent on the `deep-review` route — never the
standard `review` route. The `review.code-judo` boundary allows only
`deep-review`, so a mistaken standard-route request fails closed rather than
silently downgrading the model.

## Required Context

Read before starting: `rules/code-review.md`, `rules/stop-rules.md`.
Input: the diff (uncommitted, committed range, or PR) and, when available, the
change title / commit subjects. This lens emits unscored **proposals**, not
severity-tagged findings, so the toolkit severity scale is deliberately absent
from this contract — do not import it, and do not tag proposals with severities.

## The Task

For the changeset, answer one question: **is there a "code-judo" move — a
restructuring that preserves behavior while making the implementation
dramatically simpler, smaller, and more direct?** A code-judo move *deletes*
complexity rather than relocating it: whole branches, helpers, modes,
conditionals, or layers disappear because the change is reframed to use the
existing architecture more effectively.

Be ambitious. Do not stop at "this could be a bit cleaner." Look for the
reframing that makes the change feel inevitable in hindsight. If there is a path
to a much simpler idea — not just a cleaner version of the same messy idea —
propose it.

## Hard Confidence Bar

Only surface a proposal that **names the concrete complexity it removes**. Every
proposal must state, explicitly:

1. **What disappears** — the specific branches, helpers, states, casts, or files
   the restructuring deletes (with `file:line` anchors in the current diff).
2. **The reframing** — the smaller model/flow that replaces them, concretely
   enough that a reader could implement it.
3. **Behavior-preservation argument** — why the observable behavior is unchanged,
   and the one place that argument is weakest.

A proposal that cannot fill in all three is a vague "feels cleaner" nudge — drop
it. Do not pad the output with rename-level suggestions; a single high-conviction
restructuring beats five soft ones. If the diff has no available code-judo move,
say so plainly ("no structural simplification found; the change is already close
to minimal") — a clean result is a valid and valuable output.

## Where to Look

- A complicated implementation where a cleaner reframing deletes whole categories
  of complexity.
- Refactors that move code around but do not reduce the number of concepts a
  reader must hold in their head.
- Repeated conditionals or scattered special cases that signal a missing model,
  dispatcher, or policy object.
- A feature threaded through shared code with checks, where a boundary change
  would make it a natural extension of an existing abstraction instead.
- Generic "magic" handling that hides simple structure; thin wrappers and
  identity abstractions that add indirection without buying clarity.
- Casts, optionality, or ad-hoc object shapes that exist only because a boundary
  was left implicit — where an explicit typed model would collapse the control
  flow.

## Preferred Moves

In rough order of value: delete a layer of indirection rather than polish it;
reframe the state model so conditionals disappear instead of getting centralized;
change the ownership boundary so the feature becomes a natural extension of an
existing abstraction; turn special cases into a simpler default flow with fewer
exceptions; replace condition chains with a typed model or explicit dispatcher;
separate orchestration from business logic; make a type boundary explicit so the
control flow simplifies.

## Output

For each proposal (0, 1, or 2 — quality over quantity):

```markdown
### Proposal: [one-line restructuring]
Deletes: [concrete branches/helpers/states/files + file:line]
Reframing: [the smaller model/flow that replaces them]
Behavior preserved because: [argument] — weakest point: [the one risk]
Effort / blast radius: [rough size of the restructure]
```

Frame every proposal as a **recommendation requiring behavior-preserving
verification**, never an assertion that the current code is wrong. If a proposal
cannot be shown behavior-preserving from the diff alone, say so and name what
would need to be checked. Apply the stop rules in `rules/stop-rules.md`.

### Routed result mapping

This lane runs through `model-run`, whose result contract is the same four fields
every route returns — `status`, `summary`, `findings`, `verification`. That
contract has no proposals field, so pin the mapping here rather than leaving each
worker to guess:

- `summary` — the proposal blocks above, verbatim and in full, concatenated when
  there are two. A clean result puts the "no structural simplification found"
  sentence here instead.
- `findings` — **always empty**. Proposals are unscored; a proposal written into
  `findings` becomes a severity-graded finding in every consumer downstream, which
  is precisely what this lens's separation from the findings lenses exists to
  prevent. Emitting a non-empty `findings` array from this lane is a contract
  violation, not a formatting choice.
- `verification` — the behavior-preservation checks a reader must run before
  acting on a proposal, including the ones this pass could not complete from the
  diff alone.

The caller keeps that split when it ingests the result: `summary` goes to the
Restructuring Proposals section of the Review Record, never the findings table.
