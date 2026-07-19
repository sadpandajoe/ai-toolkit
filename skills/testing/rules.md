# Testing Rules

Read this when running automated test suites or choosing test worker counts.

## Worker Management

Before running Jest, pytest, Playwright, or similar test suites:
1. Check system resources, including CPU count and available memory.
2. Check Docker load with `docker ps`.
3. Choose worker counts based on current resource pressure.

| Condition | Worker count | Example flag |
|-----------|--------------|--------------|
| Docker stack running | 2 | `--maxWorkers=2` |
| No Docker, light usage | 4 | `--maxWorkers=4` |
| Single test file | 1-2 | `--maxWorkers=2` |
| Full suite, nothing else running | 50% of CPUs | `--maxWorkers=50%` |

<!-- aitk-model-route-exempt:test-runner-process-workers -->
Always pass `--maxWorkers` to Jest. The default can spawn too many workers and cause OOM crashes.

For pytest, use `-n` with pytest-xdist following the same worker guidelines, or omit it for sequential runs.

For Playwright, inspect `playwright.config.ts` before running broad suites; respect the configured worker strategy unless there is a clear reason to override it.
