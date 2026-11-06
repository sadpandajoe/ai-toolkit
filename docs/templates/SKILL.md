---
name: <folder-name>
description: <What it does, in one clause>. Use when <the phrases and situations a user actually brings, including ones that don't name the skill>. Do NOT use for <the nearest sibling cases, naming the skill that owns each>.
---

# <Skill Name>

<!--
Copy to skills/<name>/SKILL.md, then delete every comment.

- The description is the only trigger: there is no router. It carries every
  "when"; the body never repeats it.
- Every line must pass the admission rule (AGENTS.md): a fact the model can't
  infer, a boundary a hook or script enforces, a format code parses, or a
  portability shim. Procedure a current model already follows ("reproduce
  first", "write a failing test", "read the code") does not belong here.
- Say why a fact matters when it isn't obvious; a stated reason travels to
  cases the text did not list.
- Keep it short: about 250-600 words. A long fact list (gotchas, an API
  query) goes in references/, linked from where it is needed.
- Name no model here; agents/ and skills/review/scripts/second-opinion.py pin
  models.
-->

<One or two sentences: what the outcome is and where it stops.>

## <Facts>

<!-- The things the model would otherwise get wrong: hosts, commands, APIs,
     incidents, the user's thresholds and preferences. -->
- <Fact, and the reason when it is not obvious.>

## <Boundaries>

<!-- Omit unless this skill authorizes or forbids something beyond
     rules/universal.md. -->
- <What invoking this skill authorizes, or a trap and what to do instead.>
