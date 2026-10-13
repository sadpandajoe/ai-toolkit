---
name: <folder-name>
description: <What it does, in one clause>. Use when <the phrases and situations a user actually brings, including ones that don't name the skill>. Do NOT use for <the nearest sibling cases, naming the skill that owns each>.
---

# <Skill Name>

<!--
Copy to skills/<name>/SKILL.md, then delete every comment.

How this template is meant to be read by the model that loads the skill:
- The description is the only part seen before the skill loads. It decides
  routing, so it carries every "when"; the body never repeats it.
- Say why a step matters instead of shouting it. A current model follows a
  stated reason further than it follows MUST or NEVER, and applies it to
  cases the text did not list.
- State the outcome and the boundary, then trust the model with the method.
  Write steps only where order or an exact command matters.
- Keep this file a router: under about 150 lines. Detail a single phase needs
  goes in references/, linked from that phase, so it loads only there.
- Name no model, effort, or provider here. Routes come from
  interfaces/model-routing.json; provider syntax lives in adapters.
-->

> **Produces**: <the artifact or state change the caller gets back>.

## Contract

<Two to five sentences: the goal, what is in scope, what is out, and why the
boundary sits there. This is what the model falls back on for any case the
steps do not cover.>

Effect: `<read_only | local_mutation | git_mutation | external_effect>`.

<!-- Only for external_effect, and say exactly what the invocation grants: -->
Authorization mode: `<invocation | explicit>`. <What invoking this skill
authorizes, and what it does not.>

## Before Starting

<!-- Omit when there is nothing to read first. -->
- Read <sibling file> for <the reason>. <!-- link the sibling file so it loads only here -->

## Steps

<!-- Use "## Phases" with a table of phase → reference instead when the skill
     is an umbrella over several references. -->
1. **<Outcome of step>.** <What to do, and the reason when it is not obvious.>
2. **<Outcome of step>.** <Link the reference this step needs.>

## Output

<The shape returned to the caller, or a link to templates/<shape>.md. Say
where it is written when it is a file.>

## Boundaries

<!-- Omit when the Contract already says it. -->
- <A trap the model would plausibly walk into, and what to do instead.>
