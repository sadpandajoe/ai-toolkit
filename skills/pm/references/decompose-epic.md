---
tier: Heavy
---

# Decompose Epic into Wave Plan

> **Input**: Epic reference (Shortcut epic, GitHub milestone, or plain-text multi-feature request)
> **Output**: Wave plan — stories grouped into dependency-ordered waves

Called by `create-feature` when the input contains multiple stories.

## Steps

### 1. Fetch and Parse

| Input type | How to fetch |
|-----------|-------------|
| Shortcut epic URL/ID | Fetch epic + all stories via Shortcut API |
| GitHub milestone URL | `gh issue list --milestone <name> --json number,title,body,labels` |
| GitHub project URL | `gh project item-list <number> --format json` |
| Plain-text multi-feature | Extract individual features from the description |

For each story extract: **ref** (ID/URL), **title**, **type** (API / migration / frontend / backend / infra / config), **description**, **acceptance criteria** (if available).

### 2. Build Dependency Graph

For each story, identify what it **produces** and what it **consumes**:

| Produces | Implies dependency from consumers |
|----------|----------------------------------|
| New DB table / migration | Anything reading that table or using new columns |
| New API endpoint | Frontend or services consuming it |
| Shared type / component / library | Features importing it |
| Config / infra / auth change | Features that need it to function |

Dependency = story B consumes what story A produces → `A → B`.

Also check for **implicit dependencies**:
- If two stories modify the same file, they conflict — put the simpler/foundational one earlier
- Migration ordering matters — schema changes before data migrations

### 3. Sort into Waves

Topological sort on the dependency graph:

- **Wave 1**: Stories with zero incoming dependencies (graph roots). Typically: schema, migrations, API endpoints, shared types, config.
- **Wave N**: Stories whose dependencies are all satisfied by Waves 1..N-1.

Rules:
- All stories within a wave are independent — can run in parallel
- A wave cannot start until all previous waves' PRs are merged
- Stories with no dependencies and no dependents go in the earliest wave they fit
- If a wave has a single small story, consider collapsing it into the previous wave unless it has dependents in a later wave

### 4. Assign Branches

Pattern: `feat/<epic-slug>/<story-slug>`

Examples:
- `feat/bulk-filters/api-endpoints`
- `feat/bulk-filters/filter-panel-ui`
- `feat/bulk-filters/cache-layer`

### 5. Output Wave Plan

```markdown
## Wave Plan — [Epic Title]

**Epic**: [reference]
**Stories**: [N] across [N] waves

### Wave 1 — [theme, e.g., "Foundation"]
| # | Story | Type | Branch | Depends On |
|---|-------|------|--------|------------|
| 1 | [ref] — [title] | [type] | `[branch]` | — |

### Wave 2 — [theme, e.g., "Parallel Features"]
| # | Story | Type | Branch | Depends On |
|---|-------|------|--------|------------|
| 1 | [ref] — [title] | [type] | `[branch]` | Wave 1 |
| 2 | [ref] — [title] | [type] | `[branch]` | Wave 1 |

### Dependency Graph
[story-ref] → [story-ref]
[story-ref] → [story-ref]
```

## Notes
- Keep waves coarse — 2-4 waves is typical. More than 5 suggests over-decomposition.
- If the epic has only 1-2 stories, skip the wave plan and let `create-feature` run the standard single-story path for each.
- The wave plan is a proposal. The orchestrator (in `create-feature`) may adjust concurrency based on system resources.
