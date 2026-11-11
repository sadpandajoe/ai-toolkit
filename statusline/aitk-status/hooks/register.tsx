import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Git, Step, Usage } from '../types'

// The AI Toolkit status band: the figures `statusline/statusline-command.sh`
// prints, drawn above the prompt on every surface (terminal, desktop, vscode,
// mobile), plus the toolkit's own hook overrides.

const usage = atom({ plugin: 'aitk-status', key: 'usage' } as const, null, { shape: 'usage-1' })
const git = atom({ plugin: 'aitk-status', key: 'git' } as const, null, { shape: 'git-1' })
const step = atom({ plugin: 'aitk-status', key: 'step' } as const, null, { shape: 'step-1' })
const idleSince = atom({ plugin: 'aitk-status', key: 'idleSince' } as const, null)
const now = atom({ plugin: 'aitk-status', key: 'now' } as const, 0)
const overrides = atom({ plugin: 'aitk-status', key: 'overrides' } as const, [], { shape: 'overrides-1' })

// The user's thresholds, carried over from the bash status line.
// Context: the cost knee /usage flags is past 150k input tokens, whatever the
// window; 80% of the window is close to auto-compaction.
const CONTEXT_WARN_TOKENS = 150_000
const CONTEXT_HIGH_TOKENS = 250_000
const CONTEXT_HIGH_PERCENT = 80
// Plan windows (5h, weekly): mid-window levels are unremarkable.
const LIMIT_WARN = 70
const LIMIT_HIGH = 90
// Session cost, US dollars.
const COST_WARN = 3
const COST_HIGH = 8
// Idle past the prompt-cache TTL means the next turn re-reads the whole
// context at full price. 5 minutes is the API default; a 1-hour cache needs 60.
const CACHE_TTL_MINUTES = 5

// hooks/lib/shell_tokens.py `truthy`: unset, empty, 0, false, no and off are off.
const truthy = (value: string | undefined) =>
  value !== undefined && !['', '0', 'false', 'no', 'off'].includes(value.trim().toLowerCase())

type Tone = 'success' | 'warning' | 'error' | undefined

const tone = (value: number, warn: number, high: number): Tone =>
  value >= high ? 'error' : value >= warn ? 'warning' : 'success'

/** `claude-opus-5-5[1m]` → `Opus 5.5`; anything else as given. */
export const modelLabel = (id: string) => {
  const match = /^(?:claude-)?([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(\[[^\]]+\])?$/.exec(id)
  if (!match) return id
  const [, family = '', major, minor, context] = match
  const name = family.charAt(0).toUpperCase() + family.slice(1)
  return `${name} ${minor ? `${major}.${minor}` : major}${context ? ` ${context}` : ''}`
}

const sameModel = (a: string, b: string) =>
  a.replace(/\[[^\]]+\]$/, '') === b.replace(/\[[^\]]+\]$/, '') || modelLabel(a) === modelLabel(b)

const kilo = (tokens: number) => (tokens >= 1000 ? `${Math.round(tokens / 1000)}k` : `${tokens}`)

const bar = (percent: number) => {
  const filled = Math.max(0, Math.min(10, Math.round(percent / 10)))
  return '█'.repeat(filled) + '░'.repeat(10 - filled)
}

const span = (ms: number) => {
  const minutes = Math.max(0, Math.floor(ms / 60_000))
  if (minutes >= 1440) return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h${String(minutes % 60).padStart(2, '0')}m`
  return `${minutes}m`
}

/** `git@github.com:o/r.git`, `ssh://git@host/o/r`, `https://host/o/r.git` → https URL. */
export const webUrl = (remote: string | null) => {
  if (!remote) return undefined
  const clean = remote.trim().replace(/\.git$/, '')
  const scp = /^[\w.-]+@([^:/]+):(.+)$/.exec(clean)
  if (scp) return `https://${scp[1]}/${scp[2]}`
  const ssh = /^ssh:\/\/(?:[^@/]+@)?([^:/]+)(?::\d+)?\/(.+)$/.exec(clean)
  if (ssh) return `https://${ssh[1]}/${ssh[2]}`
  return /^https?:\/\//.test(clean) ? clean.replace(/^http:/, 'https:').replace(/\/\/[^@/]+@/, '//') : undefined
}

const readUsage = (u: {
  context: { tokens?: number; window: number; percent?: number }
  rateLimits: readonly { kind: string; percentUsed: number; resetsAt?: string }[]
  cost?: { usd: number }
}, startedAt: number): Usage => ({
  startedAt,
  tokens: u.context.tokens,
  window: u.context.window,
  percent: u.context.percent,
  costUsd: u.cost?.usd,
  limits: u.rateLimits.map(l => ({ kind: l.kind, percentUsed: l.percentUsed, resetsAt: l.resetsAt })),
})

const readGit = async ($: EngineInterface): Promise<Git | null> => {
  const cwd = await $.session.cwd()
  const run = (...args: string[]) => $.process.run(['git', '-C', cwd, ...args])
  const top = await run('rev-parse', '--show-toplevel')
  if (top.exitCode !== 0) return null
  const head = await run('symbolic-ref', '--short', 'HEAD')
  const branch =
    head.exitCode === 0 ? head.stdout.trim() : (await run('rev-parse', '--short', 'HEAD')).stdout.trim()
  const status = await run('status', '--porcelain', '--untracked-files=normal')
  const repo = await $.session.repo()
  // The main working tree's root, so a worktree shows its repository's name.
  const root = repo?.root ?? top.stdout.trim()
  return {
    branch,
    repo: root.split('/').filter(Boolean).pop() ?? root,
    web: webUrl(repo?.remote ?? null),
    changes: status.stdout.split('\n').filter(line => line.trim() !== '').length,
  }
}

async function refreshGit($: EngineInterface) {
  const value = await readGit($).catch(() => null)
  await update($, git, () => value)
}

async function tick($: EngineInterface) {
  const value = await $.clock.now()
  await update($, now, () => value)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    const started = await $.session.usage()
    await update($, usage, () => readUsage(started, started.startedAt))
    const set: string[] = []
    if (truthy(await $.env.get('AITK_PR_READY'))) set.push('PR-ready on')
    if (truthy(await $.env.get('SKIP_PRECHECK'))) set.push('pre-push checks off')
    await update($, overrides, () => set)
    const startedNow = await $.clock.now()
    await update($, now, () => startedNow)
    $.clock.every(60_000, () => void tick($))
    await refreshGit($)
    return result
  })

  on('session.measure', async ($, e, next) => {
    await update($, usage, previous => readUsage(e, previous?.startedAt ?? 0))
    return next(e)
  })

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) await update($, idleSince, () => null)
    return next(e)
  })

  // The model and effort the main loop's request really went out with: a
  // fallback or a per-turn effort shows here, not only the session's setting.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined) {
      const effort = e.effort === undefined ? undefined : String(e.effort)
      await update($, step, () => ({ model: e.model, effort }))
    }
    return yield* next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) {
      const ended = await $.clock.now()
      await update($, idleSince, () => ended)
      await refreshGit($)
    }
    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const { Box, Link, Text } = $.ui.resolve(e)
    const [u, g, s, idle, clock, flags, model, turns] = await Promise.all([
      read($, usage),
      read($, git),
      read($, step),
      read($, idleSince),
      read($, now),
      read($, overrides),
      $.session.model(),
      $.session.turns(),
    ])

    const sep = <Text dimColor> │ </Text>
    const join = (parts: (JSX.Element | null | false | undefined)[]) =>
      parts
        .filter((part): part is JSX.Element => Boolean(part))
        .flatMap((part, i) => (i === 0 ? [part] : [sep, part]))

    // Line 1: what the session runs on and what it has used.
    const served = s?.model ?? model
    const effortTone: Tone =
      s?.effort === 'max' ? 'error' : s?.effort === 'high' || s?.effort === 'xhigh' ? 'warning' : undefined
    const contextPart = u?.tokens !== undefined && (
      <Text>
        <Text dimColor>ctx </Text>
        <Text
          color={
            (u.percent ?? 0) >= CONTEXT_HIGH_PERCENT
              ? 'error'
              : tone(u.tokens, CONTEXT_WARN_TOKENS, CONTEXT_HIGH_TOKENS)
          }
        >
          {bar(u.percent ?? 0)}
        </Text>
        <Text> {kilo(u.tokens)}</Text>
        <Text dimColor>/{kilo(u.window)}</Text>
      </Text>
    )
    const limitParts = (u?.limits ?? [])
      .filter(l => l.kind === 'five_hour' || l.kind === 'seven_day' || l.kind === 'spend_limit')
      .map(l => {
        const label = l.kind === 'five_hour' ? '5h' : l.kind === 'seven_day' ? 'weekly' : 'spend'
        const resets = l.resetsAt ? Date.parse(l.resetsAt) - clock : NaN
        return (
          <Text>
            <Text dimColor>{label} </Text>
            <Text color={tone(l.percentUsed, LIMIT_WARN, LIMIT_HIGH)}>{bar(l.percentUsed)}</Text>
            <Text> {Math.round(l.percentUsed)}%</Text>
            {Number.isFinite(resets) && clock > 0 && <Text dimColor> ↻ {span(resets)}</Text>}
          </Text>
        )
      })
    const line1 = join([
      <Text>
        <Text bold>{modelLabel(served)}</Text>
        {s?.effort && <Text color={effortTone} dimColor={effortTone === undefined}> {s.effort}</Text>}
        {s && !sameModel(s.model, model) && <Text color="warning"> (fallback from {modelLabel(model)})</Text>}
      </Text>,
      contextPart,
      ...limitParts,
      u?.costUsd !== undefined && (
        <Text color={tone(u.costUsd, COST_WARN, COST_HIGH)}>${u.costUsd.toFixed(2)}</Text>
      ),
    ])

    // Line 2: where the work is, how long it has run, and what is relaxed.
    const idleMs = idle !== null && clock > 0 ? clock - idle : 0
    const line2 = join([
      g && (
        <Text>
          {g.web ? <Link href={g.web} label={g.repo} /> : <Text>{g.repo}</Text>}
          <Text dimColor> ⎇ </Text>
          {g.web ? <Link href={`${g.web}/tree/${encodeURI(g.branch)}`} label={g.branch} /> : <Text>{g.branch}</Text>}
        </Text>
      ),
      g && g.changes > 0 && <Text color="warning">{g.changes} changed</Text>,
      <Text dimColor>
        {turns} turns{u && u.startedAt > 0 && clock > 0 ? ` · ${span(clock - u.startedAt)}` : ''}
      </Text>,
      idleMs >= 60_000 && !e.props.isWorking && (
        <Text color={idleMs >= CACHE_TTL_MINUTES * 60_000 ? 'warning' : undefined} dimColor={idleMs < CACHE_TTL_MINUTES * 60_000}>
          idle {span(idleMs)}
          {idleMs >= CACHE_TTL_MINUTES * 60_000 ? ' · cache cold' : ''}
        </Text>
      ),
      ...flags.map(flag => (
        <Text color="error" bold>
          {flag}
        </Text>
      )),
    ])

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" flexWrap="wrap">
          {line1}
        </Box>
        <Box flexDirection="row" flexWrap="wrap">
          {line2}
        </Box>
      </Box>
    )
  })
}
