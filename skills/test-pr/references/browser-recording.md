# Browser Recording

Record UI evidence with `<toolkit-root>/scripts/qa/record.mjs`: a standalone
Playwright run with `recordVideo` and an injected cursor dot, producing a
`.webm` of just the browser viewport. Write only the flow, never a recorder.

```bash
node <toolkit-root>/scripts/qa/record.mjs \
  --url https://<ws>.us1a.app-stg.preset.io/ --role viewer \
  --source-id sc-NNNNN --name explore-link \
  --flow ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs   # --headless to hide the browser
```

A flow is a module whose default export drives the scenario after login:

```js
// ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs
export default async ({ page, context, url, role }) => {
  await page.getByRole('link', { name: /dashboards/i }).click();
  // ... the scenario's steps and checks
};
```

- The recorder refuses production and unknown hosts, logs in when needed
  (credentials per [preset-environments.md](preset-environments.md), never
  printed), and prints the final path once `context.close()` finalizes the
  video. Exit 2: usage error, refused host, missing credentials or Playwright.
  Exit 1: the flow or the login failed.
- Output: `~/qa-recordings/<source-id>-<short-name>-<UTC-timestamp>.webm`,
  outside any repo so `git status` stays clean.
- Reuse one Playwright install through `~/.qa-runner/` (symlink a project's
  `node_modules` there); the browser cache is shared (macOS:
  `~/Library/Caches/ms-playwright/`).
- One recording per run covering login, setup and every scenario; split only
  when the setup differs (another host, role, or data fixture).

## Traps

**The `next=` trap.** After *Log in*, do not assert with
`page.waitForURL(new RegExp(workspaceHost))`: the IdP redirect URL carries the
workspace host inside its `next=` parameter, so the regex matches while still
on the login page. Any flow that logs in again must check both clauses, as the
recorder does:

```js
const loggedIn = () => {
  const url = new URL(page.url());
  return url.hostname === WORKSPACE_HOST && !url.pathname.startsWith('/login');
};
for (let i = 0; i < 30 && !loggedIn(); i++) await page.waitForTimeout(1000);
if (!loggedIn()) throw new Error('login did not complete');
await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
```

**Key `storageState` by host AND role.** Logins are stored at
`~/.qa-runner/storage/<host>-<role>.json` (delete it to force a fresh login).
A host-only file is overwritten by a second role and reused for the first with
the wrong cookies, so requests run as the wrong user and the verdict is
invalid.

**No unscoped OS recording.** An unscoped OS-level screen recording captured
the desktop instead of the browser when the window was not on the active
space. When an OS interaction must be captured (file picker, extension popup,
notification), scope it to the browser window (macOS:
`screencapture -v -l<windowid>`).

**No webdriver spoofing in product code.** `navigator.webdriver` overrides stay
in the test browser, never in init scripts that ship.

## Playwright MCP

Playwright MCP is for interactive exploration. Recent releases can record
(`browser_start_video` / `browser_stop_video`, with `--caps=devtools`; check
the installed tool list). With `--init-script` (cursor dot), `--storage-state`
(a host-and-role file) and `--output-dir` it is an alternative; `record.mjs`
stays the primary recorder.

## Transcode

Shortcut accepts `.webm`. GitHub PR comments cap attachments around 10 MB, so
transcode for size or compatibility:

```bash
ffmpeg -y -i <file>.webm -vcodec h264 -crf 28 -preset fast -an <file>.mp4
```
