# Assess Impact

Determine the functional impact of a changeset by tracing which user-facing
workflows it touches. `review/references/classify-diff.md` assesses structure;
this asks how critical the touched behavior is. A 2-line CSS change to a login
modal is TRIVIAL by size but CORE by impact.

The caller provides the diff and the full content of the changed files.

## Steps

1. For each changed file, read the changed functions or components, follow
   imports and callers one level up, and name the user-facing workflow they
   take part in.
2. Rate each workflow. The test: does every user hit this in every normal
   session?
   - **CORE**: yes, or a failure is unrecoverable: auth, payment, data
     integrity, and the toolkit's routing or installer (`rules/gates.md`).
     In Preset and Superset: Manager login and SSO, RBAC/DAR/RLS checks,
     dashboard and chart render, SQL Lab execution, and embedded auth.
   - **STANDARD**: regular functionality that is not every-session, such as
     filters, settings, exports, notifications and search.
   - **PERIPHERAL**: low exposure, such as admin and debug tooling, internal
     metrics, docs, test fixtures and CI configuration.
3. The overall impact is the **highest** rating among the affected workflows.

## Output

```markdown
## Impact Assessment

Overall Impact: CORE / STANDARD / PERIPHERAL

### Affected Workflows
| Workflow | Criticality | Evidence |
|----------|-------------|----------|
| [workflow name] | CORE / STANDARD / PERIPHERAL | [which changed file/function participates, how] |

### Impact Reasoning
[1-2 sentences: why this impact level. What's the worst realistic user-facing consequence if this change has a bug?]
```

The evidence column is the trace from changed code to the workflow; it makes
the assessment auditable.
