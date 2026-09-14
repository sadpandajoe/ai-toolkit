# Run Tests on Changed Files

> **When**: After implementation, before review, or standalone to check the current state.
> **Produces**: Verification report with test results and confidence level.

## Effect Boundary

Effect: `read_only`.

No `@`-imports — lightweight utility. Respects `rules/resource-management.md` worker limits by convention.

## Usage

```
verify
verify src/api/
verify --files auth.ts dashboard.ts
```

Without arguments, verifies all uncommitted changes.

## Steps

### 1. Detect Changed Files

Determine the file set to verify:
- **No arguments**: `git diff --name-only` (unstaged + staged) plus untracked files
- **Directory argument**: all files under that path
- **`--files` argument**: the specified files

Filter to source files only (exclude `.md`, config, images, etc.).

### 2. Discover Test Runner

Check the project for test infrastructure:

| Indicator | Runner | Command |
|-----------|--------|---------|
| `package.json` with jest/vitest | Jest or Vitest | `npx jest` / `npx vitest run` |
| `pyproject.toml` or `setup.cfg` with pytest | pytest | `pytest` |
| `Makefile` with test target | Make | `make test` |

If multiple runners exist, pick the one matching the changed files' language.

If no runner found, report `WEAK` verification and stop.

### 3. Map Changed Files to Tests

Find test files for each changed source file using:
- Naming conventions: `foo.ts` → `foo.test.ts`, `foo.py` → `test_foo.py`
- Test directory structures: `src/foo.ts` → `tests/foo.test.ts`
- Import analysis: grep test files for imports of the changed modules

### 4. Run Tests

Run only the mapped tests, scoped to avoid full-suite overhead:

| Runner | Scoping Flag |
|--------|-------------|
| Jest | `--testPathPattern` + `--maxWorkers` per resource rules |
| Vitest | `--testPathPattern` |
| pytest | `-k` or specific test file paths, `-n` for parallel |

Check system resources before selecting worker count:
- Docker stack running → `--maxWorkers=2`
- No Docker, light usage → `--maxWorkers=4`
- Single test file → `--maxWorkers=2`

### 5. Report

Emit a verification block:

```markdown
## Verification
Runner: [jest/pytest/vitest/none]
Files changed: [N]
Tests found: [N]
Tests passed: [N] | Tests failed: [N]
Verification: STRONG / PARTIAL / WEAK — [reason]
```

**Strength tiers** (the definitions live in `rules/gates.md`, Verification
Strength; this is the same table, not a second one):
- **STRONG**: the failing or acceptance command itself (or a close equivalent)
  ran locally and passes
- **PARTIAL**: related checks that exercise the changed code ran and pass, but
  not the exact command
- **WEAK**: inspection only — no tests found or tests could not run

A failing check is never a strength: it is a `RETRY` (or `ESCALATE` by budget)
for the caller, reported with the failure output. File-to-test coverage is
reported as `Files changed / Tests found` above and does not raise the tier.

## Notes
- Report-only — does not fix failing tests. The caller owns the response.
- When called from other commands (`create-feature`, `fix-bug`), callers branch on verification strength.
- Always scope tests to changed files. Never run the full suite unless explicitly asked.
