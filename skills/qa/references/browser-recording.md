---
name: browser-recording
description: Canonical recipe for QA scenario execution — drive the browser via a standalone Playwright script with recordVideo + an injected cursor dot, producing a .webm of just the browser viewport
recommended_model: sonnet
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
- `~/qa-recordings/sc-102410-explore-link-20260505T210000Z.webm`
- `~/qa-recordings/pr-3760-smoke-20260505T210000Z.webm`

Playwright writes the file with a hash name; the script should rename it to the canonical name on completion.

### 2. Set up a runner

Reuse an existing Playwright install rather than installing fresh per run. A persistent `~/.qa-runner/` works well:

```bash
mkdir -p ~/.qa-runner
# Symlink to a known good Playwright install (e.g. one of the superset frontends)
ln -sfn /Users/joeli/opt/code/superset-private/superset-frontend/node_modules ~/.qa-runner/node_modules
```

The browser binaries cache at `~/Library/Caches/ms-playwright/` is shared across installs, so no extra download.

### 3. Write the script

A standalone ESM script that:
1. Launches Chromium in headed mode
2. Creates a context with `recordVideo: { dir, size }`
3. Calls `context.addInitScript` with the cursor-dot visualizer
4. Drives auth, navigation, and interactions
5. Closes the context (which finalizes the video file)
6. Renames the file to the canonical name

Starter template: [browser-recording/record-flow.template.mjs](browser-recording/record-flow.template.mjs). Copy and adapt per run.

### 4. Cursor + click visualizer

Inject before any page loads via `context.addInitScript`. The visualizer is a small fixed-position dot that:
- Follows `mousemove` (so the path is visible in the recording)
- Scales up briefly on `mousedown` and resets on `mouseup` (so each click reads as a distinct action)
- Lives at `z-index: 2147483647` so it stays visible over modals and overlays

The template script bundles this; don't reinvent.

### 5. Auth

Per `rules/preset-environments.md`:
- Stage: read `$PRESET_STG_BOT_LOGIN` / `$PRESET_STG_BOT_PASSWORD`. Abort with a clear message if either is unset.
- Local: try `admin`/`admin` then `admin`/`general`.
- Production: refuse.

For repeated runs, persist `storageState` between runs to skip the login leg:

```js
// First run, after successful login:
await context.storageState({ path: '~/.qa-runner/storage/<env>.json' });
// Subsequent runs:
const context = await browser.newContext({
  storageState: '~/.qa-runner/storage/<env>.json',
  recordVideo: { dir, size: VIEWPORT },
});
```

### 6. Run the script

```bash
node ~/.qa-runner/record-sc-NNNNN.mjs
```

The video is written when `context.close()` resolves. The script should print the final path on exit.

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
