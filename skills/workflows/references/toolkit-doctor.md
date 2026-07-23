# Validate Toolkit Health

## Effect Boundary

Effect: `read_only`.

Use the deterministic repository doctor. Do not reconstruct its checks manually.

## Run

From the AI Toolkit repository root:

```bash
bin/aitk doctor --strict
```

Use `--json` when another script or workflow will consume the result. A normal run exits nonzero on `FAIL`; `--strict` also treats `DRIFT` as nonzero.

## Interpret

- `PASS`: invariant is satisfied.
- `DRIFT`: generated, documented, or recommended state is stale.
- `FAIL`: safety, portability, syntax, or interface integrity is broken.

Report the failing check and its exact details. Diagnose only unless the user also asks to repair the toolkit. After an authorized repair, run `bin/aitk build`, the targeted tests, and `bin/aitk doctor --strict` again.
