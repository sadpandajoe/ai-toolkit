#!/usr/bin/env node
/**
 * Record a QA flow as a .webm of the browser viewport, with a cursor dot.
 *
 *   node <toolkit-root>/scripts/qa/record.mjs \
 *     --url https://<ws>.us1a.app-stg.preset.io/ --role viewer \
 *     --source-id sc-NNNNN --name short-flow-name --flow ./flow.mjs [--headless]
 *
 * The flow file default-exports `async ({ page, context, url, role }) => {}`
 * and drives the scenario after login. Output:
 *   ~/qa-recordings/<source-id>-<name>-<UTC timestamp>.webm
 *
 * Hosts: refuses production and unknown hosts (scripts/preset/hosts.mjs).
 * Credentials, never printed: QA_LOGIN / QA_PASSWORD when set (role-specific
 * accounts); otherwise PRESET_STG_BOT_LOGIN / PRESET_STG_BOT_PASSWORD on
 * staging, admin/admin on a local stack. Dev hosts need QA_LOGIN / QA_PASSWORD.
 * Login state is kept per host and role in ~/.qa-runner/storage/.
 *
 * Playwright: `import('playwright')`, else ~/.qa-runner/node_modules (a symlink
 * to an existing Playwright install).
 */
import { access, mkdir, rename } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { refuseProduction } from '../preset/hosts.mjs';

const USAGE = `usage: record.mjs --url <url> --role <role> --source-id <id> --name <short-name> --flow <flow.mjs> [--headless]`;
const REQUIRED = ['url', 'role', 'source-id', 'name', 'flow'];
const SAFE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const VIEWPORT = { width: 1440, height: 900 };

class UsageError extends Error {}

export function parseArgs(argv) {
  const options = { headless: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--help' || arg === '-h') return { help: true };
    if (arg === '--headless') {
      options.headless = true;
      continue;
    }
    const match = /^--([a-z-]+)(?:=(.*))?$/.exec(arg);
    if (!match || !REQUIRED.includes(match[1])) throw new UsageError(`unknown argument: ${arg}`);
    const value = match[2] ?? argv[(index += 1)];
    if (value === undefined || value === '') throw new UsageError(`--${match[1]} needs a value`);
    options[match[1]] = value;
  }
  const missing = REQUIRED.filter((key) => !options[key]);
  if (missing.length) throw new UsageError(`missing ${missing.map((key) => `--${key}`).join(', ')}`);
  for (const key of ['role', 'source-id', 'name']) {
    if (!SAFE_NAME.test(options[key])) throw new UsageError(`--${key} may use only letters, digits, '.', '_' and '-'`);
  }
  return options;
}

function credentials(environment) {
  if (process.env.QA_LOGIN && process.env.QA_PASSWORD) {
    return { login: process.env.QA_LOGIN, password: process.env.QA_PASSWORD };
  }
  if (environment === 'staging' && process.env.PRESET_STG_BOT_LOGIN && process.env.PRESET_STG_BOT_PASSWORD) {
    return { login: process.env.PRESET_STG_BOT_LOGIN, password: process.env.PRESET_STG_BOT_PASSWORD };
  }
  if (environment === 'local') return { login: 'admin', password: 'admin' };
  const names = environment === 'staging'
    ? 'PRESET_STG_BOT_LOGIN and PRESET_STG_BOT_PASSWORD (or QA_LOGIN and QA_PASSWORD)'
    : 'QA_LOGIN and QA_PASSWORD';
  throw new UsageError(`credentials not found: set ${names} in the environment`);
}

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    try {
      return createRequire(join(homedir(), '.qa-runner', 'package.json'))('playwright');
    } catch {
      throw new UsageError('Playwright not found: install it, or symlink an install to ~/.qa-runner/node_modules');
    }
  }
}

// Cursor dot: follows the mouse and pulses on click, above every overlay.
function installCursorDot() {
  const install = () => {
    if (document.getElementById('__qa_cursor__')) return;
    const dot = document.createElement('div');
    dot.id = '__qa_cursor__';
    Object.assign(dot.style, {
      position: 'fixed', width: '14px', height: '14px', borderRadius: '50%',
      background: 'rgba(255,40,80,0.9)',
      boxShadow: '0 0 0 2px rgba(255,255,255,0.95), 0 2px 6px rgba(0,0,0,0.4)',
      pointerEvents: 'none', zIndex: '2147483647',
      transform: 'translate(-50%,-50%) scale(1)',
      transition: 'transform 100ms ease-out, background 100ms ease-out',
      top: '-100px', left: '-100px',
    });
    (document.body || document.documentElement).appendChild(dot);
    addEventListener('mousemove', (event) => {
      dot.style.left = `${event.clientX}px`;
      dot.style.top = `${event.clientY}px`;
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
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
}

// Logged in: on the target host (the IdP's `next=` URL also names it) and
// not on a /login path.
function loggedIn(page, host) {
  const url = new URL(page.url());
  return url.hostname === host && !url.pathname.startsWith('/login');
}

async function logIn(page, host, { login, password }) {
  const email = page.locator('input[type="email"], input[name="email"], input[name="username"]').first();
  if (!(await email.isVisible({ timeout: 5000 }).catch(() => false))) return false;
  await email.fill(login);
  const secret = page.locator('input[type="password"]').first();
  if (!(await secret.isVisible({ timeout: 1500 }).catch(() => false))) {
    await page.getByRole('button', { name: /(next|continue)/i }).first().click();
    await secret.waitFor({ timeout: 15000 });
  }
  await secret.fill(password);
  await page.getByRole('button', { name: /(sign in|log in|continue|submit)/i }).first().click();
  for (let attempt = 0; attempt < 30 && !loggedIn(page, host); attempt += 1) {
    await page.waitForTimeout(1000);
  }
  if (!loggedIn(page, host)) throw new Error('login did not complete');
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  return true;
}

export async function main(argv) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(USAGE);
    return 0;
  }
  const { host, environment } = refuseProduction(options.url);
  const flowPath = resolve(options.flow);
  try {
    await access(flowPath);
  } catch {
    throw new UsageError(`flow file not found: ${options.flow}`);
  }
  const creds = credentials(environment);
  const { chromium } = await loadPlaywright();
  const { default: flow } = await import(pathToFileURL(flowPath).href);
  if (typeof flow !== 'function') throw new UsageError('the flow file must default-export a function');

  const recordings = join(homedir(), 'qa-recordings');
  const storageDir = join(homedir(), '.qa-runner', 'storage');
  await mkdir(recordings, { recursive: true });
  await mkdir(storageDir, { recursive: true });
  const storagePath = join(storageDir, `${host}-${options.role}.json`);
  const storageState = await access(storagePath).then(() => storagePath, () => undefined);
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, 'Z');
  const finalPath = join(recordings, `${options['source-id']}-${options.name}-${stamp}.webm`);

  // Hides navigator.webdriver, which some product features gate on; only in
  // this test browser, never in product code.
  const browser = await chromium.launch({
    headless: options.headless,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  let video;
  try {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      recordVideo: { dir: recordings, size: VIEWPORT },
      storageState,
    });
    await context.addInitScript(installCursorDot);
    const page = await context.newPage();
    video = page.video();
    await page.goto(options.url, { waitUntil: 'domcontentloaded' });
    if (await logIn(page, host, creds)) await context.storageState({ path: storagePath });
    await flow({ page, context, url: options.url, role: options.role });
    await page.waitForTimeout(1500); // let the final frame land
    await context.close();
  } finally {
    await browser.close();
  }
  if (video) {
    await rename(await video.path(), finalPath);
    console.log(`recording: ${finalPath}`);
  } else {
    console.log('no video recorded');
  }
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (error) => {
      console.error(`record.mjs: ${error.message}`);
      if (error instanceof UsageError || /^refusing /.test(error.message)) {
        console.error(USAGE);
        process.exit(2);
      }
      process.exit(1);
    },
  );
}
