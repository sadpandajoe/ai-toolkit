# Cherry-Pick Plan

Per-cherry application strategy. Runs as a subagent — reasoning effort is set by the gate's difficulty classification (standard for trivial, heavy for non-trivial).

## Goal

Produce a concrete plan for how to apply this specific cherry-pick to the target branch. The plan is reviewed by the main thread before apply proceeds.

Consumes investigation output and gate decision. Do not re-litigate whether the cherry-pick should happen — the gate already decided.

## Inputs

- Investigation output (source analysis, target compat, prereq scan, file lists)
- Gate decision (difficulty tier, adapt required, any force-override warnings)
- Target branch name

## Plan Contents

### 1. File Strategy

- **Include list**: files from the source commit that apply to the target
- **Exclude list**: files to exclude and why (CI configs, submodule pointers, files not relevant)
- **Modify/delete files**: files that exist on source but not target — need `git rm` during apply

### 2. Conflict Forecast

- **Expected conflicts**: from investigation's target compat scan, list files likely to conflict and why
- **Resolution approach per file**: adapt to target API, import path fix, trivial rename, etc.
- **Unknown risks**: areas where investigation couldn't determine compatibility

### 3. Adaptation Strategy (non-trivial only)

- **API differences**: target-side APIs that differ, how to adapt
- **Import/module changes**: paths or modules that need updating
- **Logic adaptation**: behavioral changes needed to fit target architecture
- **Scope boundary**: what parts of the commit to include, what to drop

### 4. Validation Approach

- **Minimum checks**: lint/type-check commands to run
- **Targeted tests**: specific test files/suites covering the changed area
- **Build verification**: whether a build step is needed
- **Gaps**: validation that would be ideal but requires environment setup

## Output

Fill in the template at [../assets/plan-template.md](../assets/plan-template.md). The execution table is required for every cherry-pick (single or batch) — it's the tracking artifact that follows the cherry through apply → adapt → validate.

## Plan Review Cycle

The main thread reviews. If feedback comes back:

1. Read the feedback carefully
2. Revise the plan to address concerns
3. Re-emit the full plan (not just changed sections)
4. Repeat until approved

Common review feedback:
- "Missing file X from exclude list" → add with justification
- "Conflict approach for Y is wrong, target uses Z API" → revise adaptation strategy
- "Risk is understated" → re-evaluate and adjust
- "This should be rejected, not planned" → plan does not override gate, but can note disagreement for the reviewer

## Adaptation Severity Definitions

Used in execution tables across cherry-pick phases:

- `None` = applied mechanically, no conflict resolution
- `Minor` = resolved import paths, renamed variables, or trivial API differences
- `Medium` = rewrote logic to fit target-side APIs or extracted functional subset from a mixed commit
- `High` = dropped significant chunks (entire functions, files, or bug fixes) because the target lacks required architecture. Requires user awareness — always pair with detailed notes.

## Bundled PRs

When a single PR contains multiple independent fixes:
- List each sub-fix and its applicability to the target
- Recommend which to include/exclude
- If sub-fixes are entangled, treat atomically
- Note in plan: "N of M sub-fixes planned for inclusion"
