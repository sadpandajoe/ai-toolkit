#!/usr/bin/env node
/**
 * Seed the canonical RBAC test users on a Preset staging or dev workspace
 * through the Manager API (skills/preset-rbac-setup/SKILL.md).
 *
 *   node <toolkit-root>/scripts/preset/setup-rbac.mjs --host <workspace-host-or-url> \
 *     [--apply] [--replace-existing] [--headless]
 *
 * Dry run by default: discovery and a plan table, no writes. `--apply` makes
 * the role and data-access-role (DAR) changes in that plan, after checking
 * discovery has not changed since; `--replace-existing` (only with `--apply`)
 * also deletes stale toolkit-owned DARs. DARs are named `AI Toolkit RBAC
 * <username>`, so a rerun updates the same permission. Unrelated permissions
 * are never touched.
 *
 * Hosts: workspace hosts on app-stg or app-dev only (scripts/preset/hosts.mjs);
 * the Manager is manage.app-stg.preset.io or manage.app-dev.preset.io.
 * Credentials, never printed: QA_LOGIN / QA_PASSWORD when set, otherwise
 * PRESET_STG_BOT_LOGIN / PRESET_STG_BOT_PASSWORD on staging.
 * Auth: the Manager token (localStorage `access_token`, else the
 * `csrf_access_token` cookie) goes in `Authorization: Bearer` and, on writes,
 * in `X-CSRF-Token` with a `Referer` of the workspace URL. Each DAR write is
 * polled from SYNCING until APPLIED (or FAILED / TIMEOUT).
 */
import { access, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { refuseProduction } from './hosts.mjs';

const USAGE = 'usage: setup-rbac.mjs --host <workspace-host-or-url> [--apply] [--replace-existing] [--headless]';
export const PREFIX = 'AI Toolkit RBAC ';
export const USERS = [
  { email: 'test-primary-contributor@preset.zone', role: 'PresetAlpha', dar: true },
  { email: 'test-limited-contributor@preset.zone', role: 'PresetGamma', dar: true },
  { email: 'test-limited-contributor-no-access@preset.zone', role: 'PresetGamma', dar: false },
  { email: 'test-dashboard-viewer@preset.zone', role: 'PresetDashboardsOnly', dar: true },
  { email: 'test-dashboard-viewer-no-access@preset.zone', role: 'PresetDashboardsOnly', dar: true },
  { email: 'test-viewer@preset.zone', role: 'PresetReportsOnly', dar: true },
  { email: 'test-no-access@preset.zone', role: 'PresetNoAccess', dar: false },
];
const DATASOURCES = ['Sample Geodata', 'Flights', 'San Francisco BART Lines', 'San Francisco Population Polygons'];
export const DEFAULT_GRANTS = DATASOURCES.map((name) => ({
  resource: `database:examples:schema:public:datasource:${name}`,
  action: 'datasource_access',
}));
const MANAGERS = { staging: 'https://manage.app-stg.preset.io', dev: 'https://manage.app-dev.preset.io' };
const POLL_TRIES = 12;
const POLL_MS = 5000;

export class UsageError extends Error {}

export function parseArgs(argv) {
  const options = { apply: false, replaceExisting: false, headless: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--help' || arg === '-h') return { help: true };
    if (arg === '--apply') options.apply = true;
    else if (arg === '--replace-existing') options.replaceExisting = true;
    else if (arg === '--headless') options.headless = true;
    else if (arg === '--host' || arg.startsWith('--host=')) {
      const value = arg.includes('=') ? arg.slice(arg.indexOf('=') + 1) : argv[(index += 1)];
      if (!value) throw new UsageError('--host needs a value');
      options.host = value;
    } else throw new UsageError(`unknown argument: ${arg}`);
  }
  if (!options.host) throw new UsageError('missing --host');
  if (options.replaceExisting && !options.apply) throw new UsageError('--replace-existing needs --apply');
  return options;
}

/** The workspace host, its environment, and its Manager; refuses anything but a staging or dev workspace. */
export function target(input) {
  const { host, environment } = refuseProduction(input);
  if (!MANAGERS[environment] || host.startsWith('manage.') || !host.includes('.app-')) {
    throw new UsageError(`refusing ${host}: not a staging or dev workspace host`);
  }
  return { host, environment, managerUrl: MANAGERS[environment], workspaceUrl: `https://${host}/` };
}

export function darName(username) {
  return `${PREFIX}${username}`;
}

export function darBody(workspaceName, username, grants = DEFAULT_GRANTS) {
  return {
    workspace_name: workspaceName,
    type: 'data_access_role',
    grantees: [{ type: 'USER', identifier: username }],
    acl: { [`dar:${darName(username)}`]: { config: {}, grants } },
  };
}

function memberOf(entry) {
  const user = entry.user ?? {};
  return {
    email: String(entry.email ?? user.email ?? '').toLowerCase(),
    userId: entry.user_id ?? user.id ?? entry.id,
    username: entry.username ?? user.username,
    workspaces: entry.workspaces ?? entry.workspace_memberships ?? [],
  };
}

/** The member's current role on the workspace, or null when the payload does not say. */
export function currentRole(member, workspace) {
  for (const item of member.workspaces ?? []) {
    const id = item.workspace_id ?? item.workspace?.id ?? item.id;
    const name = item.workspace_name ?? item.workspace?.name ?? item.name;
    if (id === workspace.id || (name && name === workspace.name)) return item.role_identifier ?? item.role ?? null;
  }
  return null;
}

const permissionName = (permission) => permission.name ?? permission.permission_name ?? '';
function grantsOf(permission, name) {
  return permission.acl?.[`dar:${name}`]?.grants ?? null;
}
const sameGrants = (left, right) => JSON.stringify(left ?? null) === JSON.stringify(right ?? null);

/**
 * Plan every change without making one. `permissions` maps a username to the
 * DARs listed for it on the workspace.
 */
export function planChanges({ workspace, memberships, permissions, users = USERS, grants = DEFAULT_GRANTS }) {
  const members = new Map(memberships.map((entry) => memberOf(entry)).map((member) => [member.email, member]));
  return users.map((spec) => {
    const member = members.get(spec.email.toLowerCase());
    if (!member) return { email: spec.email, status: 'NOT_A_MEMBER', role: { action: 'none' }, dar: { action: 'none' }, delete: [], kept: [] };
    const listed = permissions[member.username] ?? [];
    const name = darName(member.username);
    const owned = listed.filter((permission) => permissionName(permission).startsWith(PREFIX));
    const kept = listed.filter((permission) => !permissionName(permission).startsWith(PREFIX)).map(permissionName);
    const current = currentRole(member, workspace);
    const role = current === spec.role
      ? { action: 'none', current, proposed: spec.role }
      : { action: 'PUT', current: current ?? 'unknown', proposed: spec.role };
    let dar = { action: 'none', name: spec.dar ? name : null };
    const remove = [];
    for (const permission of owned) {
      const ownedName = permissionName(permission);
      if (spec.dar && ownedName === name) {
        if (!sameGrants(grantsOf(permission, name), grants)) dar = { action: 'PUT', name };
      } else {
        remove.push(ownedName);
      }
    }
    if (spec.dar && !owned.some((permission) => permissionName(permission) === name)) dar = { action: 'POST', name };
    return {
      email: spec.email,
      username: member.username,
      userId: member.userId,
      status: 'PLANNED',
      role,
      dar,
      delete: remove,
      kept,
    };
  });
}

export function formatPlan(plan, { replaceExisting = false } = {}) {
  const lines = ['user\tcurrent role\tproposed role\tDAR action\tpermission\tdeletion candidates'];
  for (const row of plan) {
    if (row.status === 'NOT_A_MEMBER') {
      lines.push(`${row.email}\tNOT_A_MEMBER\t-\t-\t-\t-`);
      continue;
    }
    const removal = row.delete.length ? `${row.delete.join(', ')}${replaceExisting ? '' : ' (kept without --replace-existing)'}` : '-';
    lines.push(
      [row.email, row.role.current ?? '-', row.role.action === 'none' ? `${row.role.proposed} (unchanged)` : row.role.proposed,
        row.dar.action, row.dar.name ?? '-', removal].join('\t'),
    );
  }
  return lines.join('\n');
}

/** A Manager client over `send(method, url, { headers, body }) -> { status, json }`. */
export function managerApi({ managerUrl, token, referer, send }) {
  const request = async (method, path, body) => {
    const headers = { Accept: 'application/json', Authorization: `Bearer ${token}` };
    if (method !== 'GET') {
      headers['X-CSRF-Token'] = token;
      headers.Referer = referer;
      if (body !== undefined) headers['Content-Type'] = 'application/json';
    }
    const response = await send(method, `${managerUrl}${path}`, { headers, body: body === undefined ? undefined : JSON.stringify(body) });
    if (response.status >= 400) throw new Error(`${method} ${path} returned ${response.status}`);
    return response.json;
  };
  return {
    get: (path) => request('GET', path),
    put: (path, body) => request('PUT', path, body),
    post: (path, body) => request('POST', path, body),
    delete: (path) => request('DELETE', path),
  };
}

const list = (payload) => (Array.isArray(payload) ? payload : payload?.payload ?? payload?.result ?? payload?.data ?? []);
const team = (slug) => `/api/v1/teams/${encodeURIComponent(slug)}`;

/** Find the workspace's team, its members, and each member's DARs on it. */
export async function discover(api, host) {
  for (const entry of list(await api.get('/api/v1/teams/'))) {
    const slug = entry.name ?? entry.slug;
    const workspace = list(await api.get(`${team(slug)}/workspaces/`)).find((item) => item.hostname === host);
    if (!workspace) continue;
    const memberships = list(await api.get(`${team(slug)}/memberships/`));
    const permissions = {};
    for (const entry of memberships) {
      const member = memberOf(entry);
      if (!USERS.some((spec) => spec.email === member.email) || !member.username) continue;
      const query = new URLSearchParams({
        workspace_name: workspace.name,
        permission_type: 'data_access_role',
        grantee_identifier: member.username,
      });
      permissions[member.username] = list(await api.get(`${team(slug)}/permissions/?${query}`));
    }
    return { slug, workspace, memberships, permissions };
  }
  throw new Error(`no team the bot belongs to owns ${host}`);
}

export async function waitApplied(api, slug, name, { tries = POLL_TRIES, delay = POLL_MS, sleep } = {}) {
  const pause = sleep ?? ((ms) => new Promise((done) => setTimeout(done, ms)));
  let state = 'SYNCING';
  for (let attempt = 0; attempt < tries; attempt += 1) {
    const permission = await api.get(`${team(slug)}/permissions/${encodeURIComponent(name)}`);
    state = String(permission?.status ?? permission?.state ?? 'SYNCING').toUpperCase();
    if (['APPLIED', 'FAILED', 'TIMEOUT'].includes(state)) return state;
    await pause(delay);
  }
  return 'TIMEOUT';
}

/** Make the planned changes; deletions only with `replaceExisting`. */
export async function applyPlan(api, discovery, plan, { replaceExisting = false, grants = DEFAULT_GRANTS, poll = {} } = {}) {
  const { slug, workspace } = discovery;
  const results = [];
  let mutations = 0;
  for (const row of plan) {
    if (row.status === 'NOT_A_MEMBER') {
      results.push({ email: row.email, status: 'NOT_A_MEMBER' });
      continue;
    }
    let status = 'UNCHANGED';
    try {
      if (row.role.action === 'PUT') {
        await api.put(`${team(slug)}/workspaces/${encodeURIComponent(workspace.id)}/membership`, {
          role_identifier: row.role.proposed,
          user_id: row.userId,
        });
        mutations += 1;
        status = 'UPDATED';
      }
    } catch (error) {
      results.push({ email: row.email, status: 'ROLE_FAILED', detail: error.message });
      continue;
    }
    try {
      if (row.dar.action === 'POST' || row.dar.action === 'PUT') {
        const body = darBody(workspace.name, row.username, grants);
        if (row.dar.action === 'POST') await api.post(`${team(slug)}/permissions/`, body);
        else await api.put(`${team(slug)}/permissions/${encodeURIComponent(row.dar.name)}`, body);
        mutations += 1;
        const state = await waitApplied(api, slug, row.dar.name, poll);
        if (state !== 'APPLIED') throw new Error(`${row.dar.name} ended ${state}`);
        status = 'UPDATED';
      }
      if (replaceExisting) {
        for (const name of row.delete) {
          await api.delete(`${team(slug)}/permissions/${encodeURIComponent(name)}`);
          mutations += 1;
          status = 'UPDATED';
        }
      }
    } catch (error) {
      results.push({ email: row.email, status: 'DAR_FAILED', detail: error.message });
      continue;
    }
    results.push({ email: row.email, status });
  }
  return { results, mutations };
}

export function formatResults({ results, mutations }) {
  const lines = ['user\tstatus\tdetail', ...results.map((row) => `${row.email}\t${row.status}\t${row.detail ?? '-'}`)];
  lines.push(`mutations: ${mutations}`);
  return lines.join('\n');
}

function credentials(environment) {
  if (process.env.QA_LOGIN && process.env.QA_PASSWORD) return { login: process.env.QA_LOGIN, password: process.env.QA_PASSWORD };
  if (environment === 'staging' && process.env.PRESET_STG_BOT_LOGIN && process.env.PRESET_STG_BOT_PASSWORD) {
    return { login: process.env.PRESET_STG_BOT_LOGIN, password: process.env.PRESET_STG_BOT_PASSWORD };
  }
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

async function logIn(page, managerHost, { login, password }) {
  const signedIn = () => {
    const url = new URL(page.url());
    return url.hostname === managerHost && !url.pathname.startsWith('/login');
  };
  if (signedIn()) return false;
  const email = page.locator('input[type="email"], input[name="email"], input[name="username"]').first();
  await email.waitFor({ timeout: 15000 });
  await email.fill(login);
  await page.getByRole('button', { name: /next/i }).first().click();
  const secret = page.locator('input[type="password"]').first();
  await secret.waitFor({ timeout: 15000 });
  await secret.fill(password);
  await page.getByRole('button', { name: /log in/i }).first().click();
  for (let attempt = 0; attempt < 30 && !signedIn(); attempt += 1) await page.waitForTimeout(1000);
  if (!signedIn()) throw new Error('login did not complete');
  return true;
}

export async function main(argv) {
  const options = parseArgs(argv);
  if (options.help) {
    console.log(USAGE);
    return 0;
  }
  const site = target(options.host);
  const creds = credentials(site.environment);
  const { chromium } = await loadPlaywright();
  const managerHost = new URL(site.managerUrl).hostname;
  const storageDir = join(homedir(), '.qa-runner', 'storage');
  await mkdir(storageDir, { recursive: true });
  const storagePath = join(storageDir, `${managerHost}.json`);
  const storageState = await access(storagePath).then(() => storagePath, () => undefined);
  const browser = await chromium.launch({ headless: options.headless });
  try {
    const context = await browser.newContext({ storageState });
    const page = await context.newPage();
    await page.goto(site.managerUrl, { waitUntil: 'domcontentloaded' });
    if (await logIn(page, managerHost, creds)) await context.storageState({ path: storagePath });
    const token = (await page.evaluate(() => localStorage.getItem('access_token')))
      ?? (await context.cookies(site.managerUrl)).find((cookie) => cookie.name === 'csrf_access_token')?.value;
    if (!token) throw new Error('no Manager token: neither localStorage access_token nor the csrf_access_token cookie');
    const send = async (method, url, { headers, body }) => {
      const response = await context.request.fetch(url, { method, headers, data: body });
      const text = await response.text();
      let json = null;
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }
      return { status: response.status(), json };
    };
    const api = managerApi({ managerUrl: site.managerUrl, token, referer: site.workspaceUrl, send });
    const discovery = await discover(api, site.host);
    const plan = planChanges(discovery);
    console.log(formatPlan(plan, options));
    if (!options.apply) {
      console.log('dry run: nothing changed (pass --apply to make these changes)');
      return 0;
    }
    const again = planChanges(await discover(api, site.host));
    if (JSON.stringify(again) !== JSON.stringify(plan)) {
      console.error('discovery changed between the plan and --apply; nothing changed, rerun to see the new plan');
      return 1;
    }
    const outcome = await applyPlan(api, discovery, plan, options);
    console.log(formatResults(outcome));
    return outcome.results.some((row) => row.status.endsWith('_FAILED')) ? 1 : 0;
  } finally {
    await browser.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (error) => {
      const usage = error instanceof UsageError || /^refusing /.test(error.message);
      console.error(usage ? `${error.message}\n${USAGE}` : `setup-rbac: ${error.message}`);
      process.exit(usage ? 2 : 1);
    },
  );
}
