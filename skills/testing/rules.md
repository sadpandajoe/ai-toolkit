# Testing Rules

Read this when running automated test suites or choosing test worker counts.

## Worker Management

Before a broad run of Jest, pytest, Playwright, or a similar suite, check the
machine's free memory and CPU and whether a Docker stack is running
(`docker ps`), and size the worker count to that measured headroom rather than
to a fixed table or a share of CPUs. With a Docker stack up, start at two
workers and raise the count only while memory stays comfortable.

<!-- aitk-model-route-exempt:test-runner-process-workers -->
Always pass `--maxWorkers` to Jest. The default can spawn too many workers and cause OOM crashes.

For pytest, use `-n` with pytest-xdist sized the same way, or omit it for sequential runs.

For Playwright, inspect `playwright.config.ts` before running broad suites; respect the configured worker strategy unless there is a clear reason to override it.
