# Code-Judo (Structural Restructuring Proposal)

A **generative** pass, not a findings pass: it proposes a concrete
behavior-preserving restructuring that makes the change dramatically simpler.
It returns unscored proposals; do not tag them with severities.

<!-- aitk-model-route:review.code-judo -->
Dispatch a single code-judo agent on the `deep-review` route, with the diff
and, when available, the change title or commit subjects.

## The Task

Answer one question: **is there a "code-judo" move — a restructuring that
preserves behavior while making the implementation dramatically simpler,
smaller, and more direct?** A code-judo move *deletes* complexity rather than
relocating it: whole branches, helpers, modes, conditionals, or layers
disappear because the change is reframed to use the existing architecture
more effectively. Look for the reframing that makes the change feel
inevitable in hindsight, not a cleaner version of the same idea: delete a
layer instead of polishing it, reframe state so conditionals disappear, or
make an implicit type boundary explicit so casts and branches collapse.

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
it, along with rename-level suggestions. Most diffs have no move or one; report
each proposal that clears the bar. If the diff has no available code-judo move,
say so plainly ("no structural simplification found; the change is already close
to minimal") — a clean result is a valid and valuable output.

## Output

For each proposal:

```markdown
### Proposal: [one-line restructuring]
Deletes: [concrete branches/helpers/states/files + file:line]
Reframing: [the smaller model/flow that replaces them]
Behavior preserved because: [argument] — weakest point: [the one risk]
Effort / blast radius: [rough size of the restructure]
```

Frame every proposal as a recommendation requiring behavior-preserving
verification, never an assertion that the current code is wrong.

### Routed result mapping

- `summary` — the proposal blocks above, verbatim, or the "no structural
  simplification found" sentence. The caller files it under Restructuring
  Proposals in the Review Record, never in the findings table.
- `findings` — **always empty**; proposals are unscored and `model-run`
  rejects a non-empty array on this boundary.
- `verification` — the behavior-preservation checks a reader must run before
  acting on a proposal, including the ones this pass could not complete.
