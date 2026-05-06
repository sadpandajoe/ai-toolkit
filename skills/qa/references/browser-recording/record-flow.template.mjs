#!/usr/bin/env node
/**
 * Template: Playwright-driven QA recording with cursor-dot visualizer.
 *
 * Copy to ~/.qa-runner/record-<source-id>-<short-name>.mjs, adapt the FLOW
 * section, and run:
 *   node ~/.qa-runner/record-<source-id>-<short-name>.mjs
 *
 * Output: ~/qa-recordings/<source-id>-<short-name>-<UTC-timestamp>.webm
 *
 * Prerequisite: ~/.qa-runner/node_modules symlinked to a Playwright install,
 * e.g. /Users/joeli/opt/code/superset-private/superset-frontend/node_modules.
 */
import { chromium } from 'playwright';
import { mkdir, rename } from 'node:fs/promises';
import { homedir } from 'node:os';
import { resolve } from 'node:path';

// ---- CONFIG (adapt per run) ---------------------------------------------
const SOURCE_ID = 'sc-NNNNN';                                  // e.g. sc-102410, pr-3760
const SHORT_NAME = 'short-flow-name';                          // dash-cased
const APP_URL = process.env.APP_URL || 'https://example.stg.preset.io/';
const STG_LOGIN = process.env.PRESET_STG_BOT_LOGIN;
const STG_PASSWORD = process.env.PRESET_STG_BOT_PASSWORD;
const VIEWPORT = { width: 1440, height: 900 };
const STORAGE_PATH = resolve(homedir(), '.qa-runner/storage', new URL(APP_URL).hostname + '.json');
// --------------------------------------------------------------------------

if (!STG_LOGIN || !STG_PASSWORD) {
  console.error('Set PRESET_STG_BOT_LOGIN and PRESET_STG_BOT_PASSWORD');
  process.exit(1);
}

const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, 'Z');
const recDir = resolve(homedir(), 'qa-recordings');
await mkdir(recDir, { recursive: true });
await mkdir(resolve(homedir(), '.qa-runner/storage'), { recursive: true });

const finalName = `${SOURCE_ID}-${SHORT_NAME}-${ts}.webm`;

// `--disable-blink-features=AutomationControlled` hides `navigator.webdriver`,
// which some product features (e.g. Superset's chatbot) gate on. Scoped to the
// launched test browser only — we never inject spoofs into product code.
const browser = await chromium.launch({
  headless: false,
  args: ['--disable-blink-features=AutomationControlled'],
});

// Try to reuse storageState; fall back to fresh login.
let storageState;
try {
  await import('node:fs').then(fs => fs.promises.access(STORAGE_PATH));
  storageState = STORAGE_PATH;
  console.log('reusing storage state from', STORAGE_PATH);
} catch {
  console.log('no storage state, will sign in fresh');
}

const context = await browser.newContext({
  viewport: VIEWPORT,
  recordVideo: { dir: recDir, size: VIEWPORT },
  storageState,
});

// Cursor dot visualizer — small fixed-position div that follows the mouse
// and pulses on click. Keeps z-index high so it's visible over modals.
await context.addInitScript(() => {
  const install = () => {
    if (document.getElementById('__qa_cursor__')) return;
    const dot = document.createElement('div');
    dot.id = '__qa_cursor__';
    Object.assign(dot.style, {
      position: 'fixed',
      width: '14px', height: '14px', borderRadius: '50%',
      background: 'rgba(255,40,80,0.9)',
      boxShadow: '0 0 0 2px rgba(255,255,255,0.95), 0 2px 6px rgba(0,0,0,0.4)',
      pointerEvents: 'none', zIndex: '2147483647',
      transform: 'translate(-50%,-50%) scale(1)',
      transition: 'transform 100ms ease-out, background 100ms ease-out',
      top: '-100px', left: '-100px',
    });
    (document.body || document.documentElement).appendChild(dot);
    addEventListener('mousemove', e => {
      dot.style.left = e.clientX + 'px';
      dot.style.top = e.clientY + 'px';
    }, true);
    addEventListener('mousedown', () => {
      dot.style.transform = 'translate(-50%,-50%) scale(2.4)';
      dot.style.background = 'rgba(255,180,40,0.95)';
    }, true);
    addEventListener('mouseup', () => {
      setTimeout(() => {
        dot.style.transform = 'translate(-50%,-50%) scale(1)';
        dot.style.background = 'rgba(255,40,80,0.9)';
      }, 120);
    }, true);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install);
  } else {
    install();
  }
});

const page = await context.newPage();
await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });

// ---- AUTH ---------------------------------------------------------------
// Adapt to your IDP. Common pattern: email -> continue -> password -> submit.
const emailField = page.locator('input[type="email"], input[name="email"], input[name="username"]').first();
if (await emailField.isVisible({ timeout: 5000 }).catch(() => false)) {
  await emailField.fill(STG_LOGIN);
  const pwdField = page.locator('input[type="password"]').first();
  if (await pwdField.isVisible({ timeout: 1500 }).catch(() => false)) {
    await pwdField.fill(STG_PASSWORD);
    await page.getByRole('button', { name: /(sign in|log in|continue|submit)/i }).first().click();
  } else {
    await page.getByRole('button', { name: /(continue|next)/i }).first().click();
    await pwdField.waitFor({ timeout: 15000 });
    await pwdField.fill(STG_PASSWORD);
    await page.getByRole('button', { name: /(sign in|log in|continue|submit)/i }).first().click();
  }
  // Wait for redirect away from login
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  // Persist for next run
  await context.storageState({ path: STORAGE_PATH });
}

// ---- FLOW (replace per scenario) ----------------------------------------
// Use page.locator + role queries for resilience. Add page.waitForTimeout
// briefly between steps so the cursor dot is visible mid-flight in the video.
//
// Example skeleton:
// await page.locator('[aria-label*="chatbot" i]').click();
// await page.waitForTimeout(500);
// await page.getByRole('textbox', { name: /ask me/i }).fill('...');
// await page.keyboard.press('Enter');
// await page.getByText('expected output').first().waitFor({ timeout: 60000 });
// --------------------------------------------------------------------------

// ---- TEARDOWN -----------------------------------------------------------
await page.waitForTimeout(1500); // let final frame land
const video = page.video();
await context.close();
await browser.close();

if (video) {
  const tempPath = await video.path();
  const finalPath = resolve(recDir, finalName);
  await rename(tempPath, finalPath);
  console.log('recording:', finalPath);
} else {
  console.log('no video recorded');
}
