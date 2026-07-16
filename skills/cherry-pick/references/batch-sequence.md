---
tier: Standard
---

# Cherry-Pick Batch Sequence

Use when the user provides multiple commits or PRs. Determines execution order only — per-cherry planning is handled by [plan.md](plan.md).

## Goal

Build a safe execution order for a batch of cherry-picks. Stay lightweight — ordering and deduplication, not deep per-change analysis.

## Phase 1: Batch Pre-Flight (Bash-First)

Run deterministic discovery over the full list before asking the model to reason about ordering.

For PR inputs, gather:

```bash
gh pr view <pr> --json number,title,state,mergedAt,mergeCommit,baseRefName,headRefName,files
```

For SHA inputs, gather:

```bash
git show --stat --oneline --name-only <sha>
```

For each resolved source SHA, run quick target checks:

```bash
git log --grep="cherry picked from commit <sha>" --oneline <target-branch>
git log --grep="<pr-number-or-title-fragment>" --oneline <target-branch>
```

Classify rows mechanically before sequence planning:

| Status | Meaning | Next step |
|--------|---------|-----------|
| `ALREADY_APPLIED` | exact source-SHA `-x` marker, or explicit manifest/user decision with equivalent source evidence, exists on target | Skip |
| `NOT_MERGED` | PR is open/closed-unmerged or has no source SHA | Skip row, continue batch, surface in final report (`--step`: live decision) |
| `PREFLIGHT_BLOCKED` | PR/SHA/target/auth cannot be resolved | User decision |
| `NEEDS_INVESTIGATION` | Candidate is eligible for investigate/gate | Continue |

Write the table to the batch manifest or a local preflight file. The sequence phase consumes that table; it should not refetch the same PR metadata unless the table is incomplete.

## Parallel Work

For each `NEEDS_INVESTIGATION` candidate from the pre-flight table, run these analyses in parallel when possible:

1. **Source analysis**
   - Use the source SHA(s), PR title, and changed-file list from pre-flight.
   - Resolve PR/SHA metadata only when the pre-flight row is incomplete.
   - Inspect intent and nearby history just enough to order and triage.

2. **Dependency and overlap analysis**
   - Resolve the installed cherry-pick skill directory as `<skill-dir>`, then run `<skill-dir>/scripts/batch-deps.sh <sha1> <sha2> ...` to get the mechanical signals: per-SHA file lists, SHA pairs sharing files, per-file coverage (×N count), author-date order, and a list of fully-independent SHAs eligible for parallel investigation.
   - Read the output: every "[×2]" or higher entry in per-file coverage is a dependency point. The pairs above each describe an edge in the dependency graph.
   - Detect imports, APIs, or modules introduced by one change and consumed by another — the script's per-SHA file list surfaces this; verify by inspecting hunks for any pair flagged with shared files.

3. **Existing-fix scan**
   - Consume the target evidence from pre-flight first.
   - If pre-flight already found an exact `-x` marker or explicit manifest/user decision with equivalent source evidence, classify `Skipped` and do not run deeper checks. PR number/title grep alone is not enough to skip.
   - For SHAs with no pre-flight match, the deeper [check-existing-fix reference](../../debug/references/check-existing-fix.md) handles squashed equivalents, partial backports already in place, and fixes done independently on the target.
   - Exclude duplicates before planning order.

## Ordering Rules

- Build the dependency graph from `batch-deps.sh` output: nodes = SHAs, edges = pairs flagged as sharing files.
- Topologically sort. Author-date order from the script is a valid topo-sort *iff* no later commit reverts or replaces content from an earlier one — verify by inspecting any pair where the later commit is a `chore: remove`, `revert`, or `refactor` of code touched by the earlier commit. If you find a revert/replace pattern, swap those two.
- Independent SHAs (the script's "Independence Check" section) may be investigated in parallel — the orchestrator should spawn one subagent per island concurrently.
- Actual cherry-pick application on the target branch remains sequential.
- Flag circular dependencies or ambiguous prerequisite chains as requiring user decision.
- Do not optimize only for throughput. Prefer smaller waves when conflicts, shared files, dependency manifests, migrations, generated files, or API-shape changes appear.

**Why a real graph beats merge order:** if A modifies file F and B later removes F, applying A then B on the target requires A's adapter to integrate against the target's pre-removal F, then B's adapter to remove what's left. Applying B first (when safe by hunk inspection) lets A apply against a clean post-removal state. Merge order on master doesn't reveal this — only file-overlap analysis does.

## Dry-Run Rule

For `--plan-only`, the orchestrator also runs investigate + gate for each cherry after sequencing. This phase only handles the ordering.

## Output

```markdown
## Batch Sequence Plan

### Target Branch
<branch>

### Dependency Graph
| Change | Depends On | Independent |
|--------|------------|-------------|
| PR #123 | — | Yes |
| PR #124 | PR #123 | No |

<short summary of inter-change dependencies>

### Execution Order
| # | SHA | PR | Description | Depends On | Notes |
|---|-----|----|-------------|------------|-------|
| 1 | `<sha>` | #123 | <summary> | — | Independent |
| 2 | `<sha>` | #124 | <summary> | #123 | Must follow #123 |

### Execution Waves
| Wave | Changes | Why grouped | Execution mode |
|------|---------|-------------|----------------|
| 1 | PR #123, PR #125 | independent, low conflict | parallel investigate; sequential apply |
| 2 | PR #124 | depends on #123 | solo |

### Parallelizable Groups
[List which changes can be investigated in parallel because they're independent — copy from `batch-deps.sh` "Independence Check" section]
```

Do not populate risk, confidence, or decision fields — those belong to per-cherry investigate and gate phases.

## Full Execution Table (Batch Tracking)

The orchestrator maintains this table across all cherry-picks in a batch, updating as each per-cherry subagent completes.

See [../examples/execution-table.md](../examples/execution-table.md) for the 12-column format and field meanings.
