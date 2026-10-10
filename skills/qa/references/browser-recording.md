---
name: browser-recording
description: Canonical recipe for QA scenario execution — drive the browser via a standalone Playwright script with recordVideo + an injected cursor dot, producing a .webm of just the browser viewport
tier: Standard
---

# Browser Recording for QA

When a QA scenario needs to verify UI behavior, drive the browser via a **standalone Playwright script** with `recordVideo` enabled and a cursor-dot visualizer injected via `addInitScript`. The output is a clean `.webm` of just the browser viewport — independent of window placement, desktop spaces, or which window is foreground.

## Why this shape

- **Deterministic capture.** `recordVideo` writes the browser viewport directly via Playwright's CDP. The recording always shows the test, regardless of monitor configuration, multiple displays, or background apps.
- **Visible cursor + clicks.** Playwright drives input via CDP without rendering an OS cursor. An `addInitScript` injects a small fixed-position dot that follows `mousemove` and pulses on `click`, so the recording shows agent actions clearly.
- **Cheap to produce.** The script is the test; running it produces the artifact as a side effect. No second process, no race between recorder startup and first action.
- **MCP is for exploration, not recording.** The Playwright MCP plugin (`mcp__plugin_playwright_playwright__browser_*`) is great for interactive agent-driven browsing — snapshot, click, evaluate. It does **not** expose `recordVideo` configuration. When a recorded artifact is needed, switch to a standalone script.

## Recipe

### 1. Choose paths

Recordings go in `~/qa-recordings/` (outside any repo, so `git status` stays clean):

```
~/qa-recordings/<source-id>-<short-name>-<UTC-timestamp>.webm
```

Examples:
- `~/qa-recordings/sc-NNNNN-explore-link-20260505T210000Z.webm`
- `~/qa-recordings/pr-NNNN-smoke-20260505T210000Z.webm`

Playwright writes the file with a hash name; the recorder renames it to the canonical name on completion.

### 2. Set up a runner

Reuse an existing Playwright install rather than installing fresh per run. A persistent `~/.qa-runner/` works well:

```bash
mkdir -p ~/.qa-runner
# Symlink to a known good Playwright install for the current project
ln -sfn <path-to-playwright-project>/node_modules ~/.qa-runner/node_modules
```

The browser binaries cache at `~/Library/Caches/ms-playwright/` is shared across installs, so no extra download.

### 3. Write the flow, run the recorder

Do not write a recording script. `<toolkit-root>/scripts/qa/record.mjs` is the recorder; you write only the flow, a module whose default export drives the scenario after login:

```js
// ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs
export default async ({ page, context, url, role }) => {
  await page.getByRole('link', { name: /dashboards/i }).click();
  // ... the scenario's steps and checks
};
```

The recorder:
1. Refuses production and unknown hosts (`scripts/preset/hosts.mjs`, per `rules/preset-environments.md`)
2. Launches Chromium headed (`--headless` to hide it)
3. Creates a context with `recordVideo: { dir, size }` and the stored login for this host and role
4. Injects the cursor-dot visualizer with `context.addInitScript`
5. Logs in when needed, then calls the flow
6. Closes the context (which finalizes the video file) and renames it to the canonical name

### 4. Cursor + click visualizer

Inject before any page loads via `context.addInitScript`. The visualizer is a small fixed-position dot that:
- Follows `mousemove` (so the path is visible in the recording)
- Scales up briefly on `mousedown` and resets on `mouseup` (so each click reads as a distinct action)
- Lives at `z-index: 2147483647` so it stays visible over modals and overlays

`<toolkit-root>/scripts/qa/record.mjs` bundles this; don't reinvent.

### 5. Auth

Per `rules/preset-environments.md`, as the recorder applies it:
- `QA_LOGIN` / `QA_PASSWORD`, when both are set, win on any allowed host. Use them for multi-role / RBAC runs, with role-specific credentials from your team's secrets vault (e.g. `Agor-Test-Vault`); never hard-code per-role passwords.
- Stage: `$PRESET_STG_BOT_LOGIN` / `$PRESET_STG_BOT_PASSWORD`. The recorder stops with a clear message if they are unset.
- Dev: `QA_LOGIN` / `QA_PASSWORD` only; ask the user for credentials.
- Local: `admin`/`admin`. For a stack with other credentials, set `QA_LOGIN` / `QA_PASSWORD`.
- Production: refused.

The login itself is email, then *Next*, then password, as the Preset manager IdP asks.

#### Asserting login completion — the `next=` trap

After clicking *Log in*, do **not** assert with `page.waitForURL(new RegExp(workspaceHost))`. The Preset manager IdP redirects to `https://manage.app-stg.preset.io/login/?next=https%3A%2F%2F<workspaceHost>%2Fsuperset%2Fwelcome%2F` — a URL that *contains the workspace host inside the `next=` query parameter*. A naive host-substring regex matches that intermediate URL and the assertion fires while we're still on the login page, so subsequent steps (find chatbot trigger, etc.) fail with confusing timeouts.

The recorder's check, for any flow that logs in again:

```js
const loggedIn = () => {
  const url = new URL(page.url());
  return url.hostname === WORKSPACE_HOST && !url.pathname.startsWith('/login');
};
for (let i = 0; i < 30 && !loggedIn(); i++) await page.waitForTimeout(1000);
if (!loggedIn()) throw new Error('login did not complete');
await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
```

The two-clause condition (the page's own host is the workspace **and** its path is not `/login`) is what disambiguates the IdP redirect from the post-auth landing.

#### Persisting `storageState`

The recorder saves the login after a fresh sign-in and reuses it on later runs, at `~/.qa-runner/storage/<host>-<role>.json`. Delete that file to force a fresh login.

**Key the storage path by host AND role**, not by host alone. When the same workspace is exercised under multiple roles in one session (e.g. Dashboard Viewer + Primary Contributor for an RBAC verification), a host-only storage file gets overwritten by the second role's session and then silently reused for the first role's *next* run with the wrong cookies — so login is skipped, requests fire as the wrong user, and the verdict is invalid. Always include the role in the filename.

### 6. Run the recorder

```bash
node <toolkit-root>/scripts/qa/record.mjs \
  --url https://<ws>.us1a.app-stg.preset.io/ --role viewer \
  --source-id sc-NNNNN --name explore-link \
  --flow ~/.qa-runner/flows/sc-NNNNN-explore-link.mjs
```

The video is written when `context.close()` resolves; the recorder prints the final path. It exits 2 on a usage error, a refused host, missing credentials or a missing Playwright, and 1 when the flow or login fails.

### 7. Optional: transcode

Shortcut accepts `.webm` directly without practical limits. GitHub PR comments cap attachments around 10 MB; transcode to MP4 for size or compatibility:

```bash
ffmpeg -y -i <file>.webm -vcodec h264 -crf 28 -preset fast -an <file>.mp4
```

### 8. Post (only if requested)

Routing by destination:
- **Shortcut** — `skills/qa/references/write-report.md` for body shape; `skills/shortcut/references/report.md` for `/files` upload + comment posting mechanics.
- **GitHub PR** — `skills/qa/references/write-report.md` for body shape; post via `gh pr comment <pr> --body-file <path>`.
- **Local only (default)** — surface the path in the terminal summary.

## Anti-patterns

- ❌ Unscoped OS-level screen recording (`screencapture -v` / `ffmpeg avfoundation`) when the goal is to capture in-browser actions — the recording is hostage to window placement, desktop spaces, and foreground state. We tried this; the recording captured the desktop instead of the Playwright Chrome window because the window wasn't on the active space. Use Playwright `recordVideo` instead.
- ❌ Driving a recorded run via the Playwright MCP plugin — the MCP server doesn't expose `recordVideo`. MCP is for interactive exploration; recording belongs to a standalone script.
- ❌ Spoofing `navigator.webdriver` via product-code init scripts that ship outside the test session.
- ❌ Recording into the working repo — pollutes `git status`. Always use `~/qa-recordings/`.

## When OS-level recording is still appropriate

If the scenario requires capturing OS-level interactions that the page can't see — file picker dialogs, browser extension popups, OS notifications, multi-tab orchestration outside the recorded context — use `screencapture -v -l<windowid>` to record only the Playwright Chrome window. The window-id scope keeps the recording focused even when other apps pop up. Do not use unscoped `screencapture -v`; it captures the entire display and breaks when the browser isn't foreground.
