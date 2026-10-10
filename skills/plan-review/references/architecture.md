# Architecture Review

A deep code-review lens for diffs the classifier flags as an architecture
change: new module boundaries, changed public contracts, new patterns, or
cross-subsystem data flow.

Read before grading: `rules/severity.md`

Check the architecture the change ships, in code:

- For a changed public contract (API, interface, schema, event, config key),
  list every consumer with `file:line` and say whether each still holds.
- For a new pattern, name the existing pattern in the repo it duplicates, or
  the reason the existing one does not fit.
- For a moved boundary, name the caller that now crosses it and what it now
  depends on.

Code style, test details, UI specifics, and sequencing belong to other lanes.

Each finding is one string that opens with `[major]`, `[minor]`, or
`[nitpick]`, cites `file:line`, and says what goes wrong and why it matters.
Report every architectural finding you see, with your confidence when it is
less than high; the parent validates and ranks them. Improvements that are not
defects go in the summary. In `verification`, list exactly what you read or
ran.
