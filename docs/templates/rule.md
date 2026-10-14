# <Rule Name>

<!--
Copy to rules/<name>.md (or skills/<skill>/rules.md for a scoped rule), then
delete every comment.

A rule is a constraint that holds across workflows. It is not a procedure;
procedures belong in a skill. Keep it under about 60 lines, because a rule
is read on every path that links it.

- Register it: rules/universal.md is the only always-on rule
  (interfaces/guidance.json). Every other rule loads only where a skill or
  workflow phase links it, and doctor fails a rule nothing links.
- Lead with the reason. A constraint with its reason survives cases the
  rule never listed; a bare MUST does not.
- Give an absolute only when a hook enforces it, and mark it
  "(hook-enforced)" as universal.md does.
-->

<One or two sentences: what this rule governs, who reads it (every session,
the parent only, or a named phase), and why it exists.>

## Rule

- **<The constraint, stated as the behavior wanted.>** <Why: the failure it
  prevents, ideally one that happened.>
- **<Next constraint.>** <Why.>

## Applying It

<!-- Omit when the constraints are self-explanatory. -->
<How to tell when the rule applies, and the judgment call at its edge.>

## Exceptions

<!-- Omit when there are none. -->
- <When the rule yields, and to what.>
