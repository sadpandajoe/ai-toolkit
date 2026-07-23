# Show Toolkit Workflows

## Effect Boundary

Effect: `read_only`.

Use the canonical interface manifest through the CLI; do not maintain a second static command list.

```bash
bin/aitk list
```

If the current directory is not the toolkit repository, resolve `<toolkit-root>` from the installed workflows skill and run `<toolkit-root>/bin/aitk list`.

Return the output without inventing unregistered workflows. For implementation, state, resume, or gate details, point to `skills/workflows/references/<name>.md` and `interfaces/contracts.json` rather than summarizing from memory.
