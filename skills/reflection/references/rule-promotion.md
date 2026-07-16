# Rule Promotion

Use for `reflect propose-rule` and `reflect promote`.

Read `rules/rule-maintenance.md` before drafting or modifying rules.

## Propose Rule Flow

Scan recent conversation and memory files for recurring patterns:
- repeated feedback memories
- workarounds applied multiple times
- behavioral patterns that should be universal

Decision criteria:
- **Rule**: applies across projects/sessions, structural, constrains behavior
- **Memory**: project-specific, personal preference, or operational context
- **Skill lesson/gotcha**: applies only when a specific skill is active; append to that skill's `lessons.md` or `gotchas.md`

Check `rules/` for existing or partial coverage before drafting a new file.

Draft convention:
- 20-40 lines
- one concern per file
- kebab-case filename
- same heading style as existing rules

Present:

````markdown
## Proposed Rule

**Target:** `rules/{proposed-name}.md`

```markdown
{draft rule content}
```

Write this rule?
````

On confirmation:
1. Write the rule file.
2. Remind user to run `./install.sh`.
3. Suggest commands that should import or reference the new rule.

## Promote Memory Flow

Accept a memory filename. If absent, display `reflect list` output and ask the user to select.

Read the memory and assess universality:
- Does this apply across projects?
- Is it structural or contextual?
- Has it appeared in other projects or conversations?

If project-specific, explain why and keep it as a memory.

If universal, check existing rules for coverage. Prefer updating an existing rule over creating a near-duplicate.

Present:

````markdown
## Proposed Rule Promotion

**Source memory:** `{memory-filename}`
**Target rule:** `rules/{proposed-name}.md`

```markdown
{draft rule content}
```

Promote this memory to a rule?
````

On confirmation:
1. Write or update the rule.
2. Delete the source memory file.
3. Remove it from `MEMORY.md`.
4. Remind user to run `./install.sh`.
5. Suggest commands that should import or reference the rule.
