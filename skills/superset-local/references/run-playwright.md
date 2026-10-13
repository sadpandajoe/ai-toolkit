# Run Playwright Local

Run Superset Playwright E2E tests against a local stack. Prerequisite: a ready
stack from `<toolkit-root>/scripts/superset-local/up.sh`
([start-stack.md](start-stack.md)), which prints `PLAYWRIGHT_BASE_URL`.

```bash
cd superset-frontend
PLAYWRIGHT_BASE_URL=http://localhost:$PORT npx playwright test [<spec>] --reporter=list
```

Keep the local `playwright.config` workers and retries; do not override them.
A test failure is reported, not retried; point to
`npx playwright show-trace <trace.zip>` when traces exist.

## Known Local Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Wrong base URL | Auth timeout on `localhost:8088` | Set `PLAYWRIGHT_BASE_URL` to the node-light host port |
| ZSTD proxy (older branches) | `ZSTDDecompress is not a function` | [start-stack.md](start-stack.md#3-zstd-proxy-setting) |
| First-run auth timeout | Global setup fails, then works on retry | Transient: retry the run once |
| Stale tab state | Tab count assertions off | Tests should use relative counts, not absolute |
| Missing browser | `browserType.launch` fails | Run `npx playwright install chromium` |

Report base URL, passed / failed / total, duration, and each failure as
`[file] › test name — error`.
