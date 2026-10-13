# Browser Recording for QA

When a QA scenario needs to verify UI behavior, record it with the toolkit's
recorder, `<toolkit-root>/scripts/qa/record.mjs`: a standalone Playwright run
with `recordVideo` and an injected cursor dot, producing a `.webm` of just the
browser viewport, whatever the window placement or foreground app. Do not
write a recording script; write only the flow.

Make one recording per run; split only when the setup differs (another host,
role, or data fixture).

## Paths

Recordings go in `~/qa-recordings/`, outside any repo, so `git status` stays
clean:

```
~/qa-recordings/<source-id>-<short-name>-<UTC-timestamp>.webm
```

The recorder renames Playwright's hashed file to this name. Reuse one
Playwright install through `~/.qa-runner/` (symlink a project's
`node_modules` there); the browser cache is shared across installs
(macOS: `~/Library/Caches/ms-playwright/`).

## Flow and Run

A flow is a module whose default export drives the scenario after login:

```js
// ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs
export default async ({ page, context, url, role }) => {
  await page.getByRole('link', { name: /dashboards/i }).click();
  // ... the scenario's steps and checks
};
```

```bash
node <toolkit-root>/scripts/qa/record.mjs \
  --url https://<ws>.us1a.app-stg.preset.io/ --role viewer \
  --source-id sc-NNNNN --name explore-link \
  --flow ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs
```

The recorder refuses production and unknown hosts
(`rules/preset-environments.md`), runs headed (`--headless` to hide it),
injects the cursor dot (follows `mousemove`, pulses on click, top `z-index`),
logs in when needed, calls the flow, and prints the final path once
`context.close()` finalizes the video. It exits 2 on a usage error, a refused
host, missing credentials or a missing Playwright, and 1 when the flow or
login fails.

Credentials follow `rules/preset-environments.md`: `QA_LOGIN` / `QA_PASSWORD`
win on any allowed host (role-specific values come from the team's secrets
vault, never hard-coded); staging uses `$PRESET_STG_BOT_LOGIN` /
`$PRESET_STG_BOT_PASSWORD`; dev needs `QA_LOGIN` / `QA_PASSWORD`; local stacks
use `admin`/`admin`. The login is email, then *Next*, then password.

## Traps

**The `next=` trap.** After *Log in*, do not assert with
`page.waitForURL(new RegExp(workspaceHost))`: the IdP redirect URL carries the
workspace host inside its `next=` parameter, so the regex matches while still
on the login page. The recorder's check, for any flow that logs in again:

```js
const loggedIn = () => {
  const url = new URL(page.url());
  return url.hostname === WORKSPACE_HOST && !url.pathname.startsWith('/login');
};
for (let i = 0; i < 30 && !loggedIn(); i++) await page.waitForTimeout(1000);
if (!loggedIn()) throw new Error('login did not complete');
await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
```

Both clauses matter: the page's own host is the workspace **and** its path is
not `/login`.

**Key `storageState` by host AND role.** The recorder stores logins at
`~/.qa-runner/storage/<host>-<role>.json` (delete it to force a fresh login). A
host-only file is overwritten by a second role and then reused for the first
role with the wrong cookies, so requests run as the wrong user and the verdict
is invalid.

**No unscoped OS recording.** An unscoped OS-level screen recording captured
the desktop instead of the browser window because the window was not on the
active space. When an OS-level interaction must be captured (file picker,
extension popup, OS notification), scope it to the browser window (macOS:
`screencapture -v -l<windowid>`).

**No webdriver spoofing in product code.** `navigator.webdriver` overrides
stay in the test browser, never in init scripts that ship.

## Playwright MCP

Playwright MCP is for interactive exploration. Recent releases can also record
(`browser_start_video` / `browser_stop_video`, enabled with `--caps=devtools`);
check the installed version's tool list first. When it can, MCP with
`--init-script` (the cursor dot), `--storage-state` (a host-and-role file) and
`--output-dir` is an alternative; `record.mjs` stays the primary recorder.

## Transcode and Post

Shortcut accepts `.webm`. GitHub PR comments cap attachments around 10 MB;
transcode for size or compatibility:

```bash
ffmpeg -y -i <file>.webm -vcodec h264 -crf 28 -preset fast -an <file>.mp4
```

Post only when asked: body shape from [write-report.md](write-report.md);
Shortcut upload and comment from `skills/shortcut/references/report.md`;
GitHub with `gh pr comment <pr> --body-file <path>`. By default, surface the
local path in the summary.
