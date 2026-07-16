---
tier: Standard
---

# Assess Impact

Determine the functional impact of a changeset by tracing which user-facing workflows it touches. This complements `review/references/classify-diff.md` (which assesses structure) with a functional lens: not "how big is the change" but "how critical is what it touches."

A 2-line CSS change to a login modal is TRIVIAL by size but CORE by impact. This phase catches that.

## Required Context

The caller provides:
- The diff (staged, unstaged, or commit range)
- Full content of changed files (not just the diff — need surrounding context to trace call paths)

## Steps

### 1. Identify Affected Code Paths

For each changed file, trace what user-facing behavior it participates in:
- Read the changed functions/components
- Follow imports and callers one level up — what invokes this code?
- Identify the user-facing workflow: login, signup, checkout, dashboard load, data save, navigation, search, API auth, permission check, etc.

### 2. Classify Workflow Criticality

Rate each affected workflow:

**CORE** — every user or every session depends on this:
- Authentication and login (including SSO, OAuth, session management)
- Authorization and permission checks
- Primary navigation and routing
- Data persistence (save, update, delete of user data)
- Payment and billing flows
- Signup and onboarding
- Core data display (main dashboard, primary list views)
- API gateway, middleware that all requests pass through
- Error boundaries and global error handling

**STANDARD** — regular functionality, not every-session:
- Secondary features (filters, sorting, bulk actions, export)
- Settings and preferences
- Notifications
- Search and discovery
- Reporting and analytics views
- Non-critical API endpoints

**PERIPHERAL** — low user exposure:
- Admin-only tooling
- Debug panels and dev tools
- Internal metrics and logging
- Documentation pages
- Test utilities and fixtures
- CI/CD configuration

### 3. Determine Overall Impact

The overall impact is the **highest criticality** among all affected workflows. If any changed code participates in a CORE workflow, the overall impact is CORE — even if most changes are PERIPHERAL.

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

## Notes
- This phase traces functional impact, not structural complexity. A one-liner in auth middleware is CORE. A 500-line refactor of an admin debug tool is PERIPHERAL.
- When uncertain whether a workflow is CORE or STANDARD, check: "does every user hit this in a normal session?" If yes → CORE.
- The evidence column is important — it shows the trace from changed code to user-facing workflow, making the assessment auditable.
- Consumed by `review-code` and `review-pr` alongside the `review` skill's classify-diff reference. Together they answer: which reviewers (classify-diff), how critical (this phase).
