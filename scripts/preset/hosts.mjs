#!/usr/bin/env node
/**
 * The one Preset host classifier (rules/preset-environments.md).
 *
 *   import { classifyHost, refuseProduction } from '<toolkit-root>/scripts/preset/hosts.mjs';
 *   classifyHost('https://<ws>.us1a.app-stg.preset.io/') // { host, environment: 'staging' }
 *
 * Environments: local, staging, dev, production, unknown. Callers treat
 * `unknown` like production: no automation against it without asking.
 *
 * CLI: node hosts.mjs <url-or-host>... prints one JSON object per argument.
 */
import { pathToFileURL } from 'node:url';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1']);

// [environment, exact hosts, domain suffixes]; a suffix needs a label before it.
const PATTERNS = [
  ['staging', ['app-stg.preset.io', 'manage.app-stg.preset.io'], ['.app-stg.preset.io']],
  ['dev', ['app-dev.preset.io', 'manage.app-dev.preset.io'], ['.app-dev.preset.io']],
  ['production', ['app.preset.io', 'manage.app.preset.io'], ['.app.preset.io']],
];

/** The lower-cased hostname of a URL or bare host, without port or trailing dot. */
export function normalizeHost(input) {
  const text = String(input ?? '').trim();
  if (!text) return '';
  let host;
  try {
    host = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `http://${text}`).hostname;
  } catch {
    return '';
  }
  return host.toLowerCase().replace(/^\[|\]$/g, '').replace(/\.$/, '');
}

export function classifyHost(input) {
  const host = normalizeHost(input);
  if (!host) return { host, environment: 'unknown' };
  if (LOCAL_HOSTS.has(host) || host.endsWith('.localhost')) return { host, environment: 'local' };
  for (const [environment, exact, suffixes] of PATTERNS) {
    if (exact.includes(host) || suffixes.some((suffix) => host.endsWith(suffix) && host.length > suffix.length)) {
      return { host, environment };
    }
  }
  return { host, environment: 'unknown' };
}

/** Throw unless the host is local, staging or dev. */
export function refuseProduction(input) {
  const result = classifyHost(input);
  if (!['local', 'staging', 'dev'].includes(result.environment)) {
    const why = result.environment === 'production' ? 'a production host' : 'not a known Preset test host';
    throw new Error(`refusing ${result.host || String(input)}: ${why} (rules/preset-environments.md)`);
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  for (const value of process.argv.slice(2)) {
    console.log(JSON.stringify(classifyHost(value)));
  }
}
