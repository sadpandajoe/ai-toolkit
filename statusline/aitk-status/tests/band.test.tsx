import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'aitk-status',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 120,
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

const T0 = Date.parse('2026-11-11T12:00:00Z')

const engine = (on: On, env: Record<string, string>, gh?: () => { exitCode: number; stdout: string }) => {
  const clock = mock.clock(on, { now: T0 })
  const store = new Map<string, unknown>()
  on('store.get', (_, e) => ({ value: store.get(e.key) }))
  on('store.set', (_, e) => {
    store.set(e.key, e.value)
    return { value: undefined }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  on('session.usage', () => ({
    value: { startedAt: T0 - 65 * 60_000, context: { window: 200_000 }, rateLimits: [] },
  }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.turns', () => ({ value: 12 }))
  on('session.cwd', () => ({ value: '/w/ai-toolkit' }))
  on('session.repo', () => ({
    value: { root: '/w/ai-toolkit', remote: 'git@github.com:acme/ai-toolkit.git', internal: false, name: null },
  }))
  on('env.get', (_, e) => ({ value: env[e.name] }))
  on('process.run', (_, e) => {
    if (e.argv[0] === 'gh') {
      const res = gh?.() ?? { exitCode: 1, stdout: '' }
      return { value: { ...res, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    const args = e.argv.slice(3).join(' ')
    const out: Record<string, string> = {
      'rev-parse --show-toplevel': '/w/ai-toolkit\n',
      'symbolic-ref --short HEAD': 'feat/x\n',
      'status --porcelain --untracked-files=normal': ' M a.py\n?? b.py\n',
    }
    return {
      value: { exitCode: args in out ? 0 : 1, stdout: out[args] ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    }
  })
  return { advance: clock.advance, store }
}

test('the band shows model, usage, git and overrides', async ($, on) => {
  engine(on, { SKIP_PRECHECK: '1', AITK_PR_READY: 'off' })
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'terminal', isInteractive: true })
  await $.session.measure({
    context: { tokens: 160_000, window: 200_000, percent: 80 },
    rateLimits: [{ kind: 'five_hour', percentUsed: 42, resetsAt: '2026-11-11T15:00:00Z' }],
    cost: { usd: 4.5 },
    changed: ['context', 'rateLimits', 'cost'],
  })

  for (const surface of ['terminal', 'desktop', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: 'Opus 5.5' }))?.text).toBe('Opus 5.5')
    expect((await ui.find({ type: 'Text', text: /^ctx / }))?.text).toBe('ctx ████████░░ 160k/200k')
    expect((await ui.find({ type: 'Text', text: /^5h / }))?.text).toBe('5h ████░░░░░░ 42% ↻ 3h00m')
    expect((await ui.find({ type: 'Text', text: /\$4\.50/ }))?.text).toBe('$4.50')
    expect((await ui.find({ type: 'Text', text: /2 changed/ }))?.text).toBe('2 changed')
    expect((await ui.find({ type: 'Text', text: /12 turns/ }))?.text).toBe('12 turns · 1h05m')
    expect((await ui.find({ type: 'Text', text: 'pre-push checks off' }))?.text).toBe('pre-push checks off')
    expect(await ui.find({ type: 'Text', text: 'PR-ready on' })).toBe(undefined)
    await ui.unmount()
  }
})

test('the cache countdown runs out after the TTL', async ($, on) => {
  const clock = engine(on, {})
  on('turn.complete', (_, e) => ({ text: e.answer }))
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'desktop', isInteractive: true })
  await $.turn.complete({ turnId: 't1', answer: 'done', durationMs: 1000, isAborted: false, reason: 'answer' })
  await clock.advance(7 * 60_000)

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  // the TTL is not learned yet, so it is assumed (5 minutes) and marked `?`
  expect((await ui.find({ type: 'Text', text: /^cache expired/ }))?.text).toBe('cache expired?')
  await ui.unmount()
})

test('the band yields to a survey', async ($, on) => {
  engine(on, {})
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  const survey = await $.ui.mount({ ...BAND, surface: 'desktop', props: { ...BAND.props, hasSurvey: true } })
  expect((await survey.find({ type: 'Text' }))?.text).toBe('engine')
  await survey.unmount()
})

const limit = (percentUsed: number) => ({
  context: { window: 200_000 },
  rateLimits: [{ kind: 'five_hour', percentUsed, resetsAt: '2026-11-11T15:00:00Z' }],
  changed: ['rateLimits' as const],
})

test('a plan limit toasts once at 80% and once at 95% per window', async ($, on) => {
  engine(on, {})
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'terminal', isInteractive: true })
  for (const percent of [60, 81, 83, 96, 99]) await $.session.measure(limit(percent))
  expect(toasts).toEqual(['5-hour limit at 81%', '5-hour limit at 96%'])
})

test('the band shows the last turn\'s cache hit rate', async ($, on) => {
  engine(on, {})
  on('turn.complete', (_, e) => ({ text: e.answer }))
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'terminal', isInteractive: true })
  await $.turn.complete({
    turnId: 't1',
    answer: 'done',
    durationMs: 1000,
    isAborted: false,
    reason: 'answer',
    usage: {
      model: 'claude-opus-5-5',
      input_tokens: 1_000,
      output_tokens: 500,
      cache_creation_input_tokens: 9_000,
      cache_read_input_tokens: 90_000,
    },
  })
  const ui = await $.ui.mount({ ...BAND, surface: 'mobile' })
  expect((await ui.find({ type: 'Text', text: /^cache hit / }))?.text).toBe('cache hit 90%')
  expect((await ui.find({ type: 'Text', text: /^cache .* left/ }))?.text).toBe('cache 5m left?')
  expect((await ui.find({ type: 'Text', text: /^per prompt / }))?.text).toBe('per prompt ▄ 101k · avg 101k · max 101k')
  await ui.unmount()
})

const turn = (id: string, read: number, write: number) => ({
  turnId: id,
  answer: 'done',
  durationMs: 1000,
  isAborted: false,
  reason: 'answer' as const,
  usage: { model: 'claude-opus-5-5', input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: write, cache_read_input_tokens: read },
})

test('a warm cache after a 20-minute gap teaches a 1-hour TTL, kept in the store', async ($, on) => {
  const clock = engine(on, {})
  on('turn.start', (_, e) => ({ turnId: e.turnId }) as never)
  on('turn.complete', (_, e) => ({ text: e.answer }))
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'desktop', isInteractive: true })
  await $.turn.complete(turn('t1', 0, 10_000))
  await clock.advance(20 * 60_000)
  await $.turn.start({ turnId: 't2', prompt: 'go' } as never)
  await $.turn.complete(turn('t2', 10_000, 1_000))
  expect(clock.store.get('cacheTtlMinutes')).toBe(60)

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /^cache .* left/ }))?.text).toBe('cache 1h00m left')
  expect((await ui.find({ type: 'Text', text: /^per prompt / }))?.text).toBe('per prompt ▁█ 11k · avg 11k · max 11k')
  await ui.unmount()
})

const pending = { __typename: 'CheckRun', name: 'python', status: 'IN_PROGRESS', conclusion: '' }
const view = (checks: object[]) => ({
  exitCode: 0,
  stdout: JSON.stringify({ number: 72, url: 'https://github.com/acme/ai-toolkit/pull/72', state: 'OPEN', isDraft: true, statusCheckRollup: checks }),
})

test('the PR checks show, external contexts included, and a new failure toasts', async ($, on) => {
  let checks: object[] = [pending, { __typename: 'StatusContext', context: 'jenkins', state: 'SUCCESS' }]
  engine(on, {}, () => view(checks))
  const toasts: string[] = []
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('turn.complete', (_, e) => ({ text: e.answer }))
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'terminal', isInteractive: true })

  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /^PR #72/ }))?.text).toBe('PR #72 draft ● 1 running')
  await ui.unmount()

  checks = [{ ...pending, status: 'COMPLETED', conclusion: 'FAILURE' }, { __typename: 'StatusContext', context: 'jenkins', state: 'SUCCESS' }]
  await $.turn.complete({ turnId: 't1', answer: 'done', durationMs: 1, isAborted: false, reason: 'answer' })
  expect(toasts).toEqual(['PR #72: CI failing (python)'])
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /^PR #72/ }))?.text).toBe('PR #72 draft ✗ 1 failing (python)')
  await ui.unmount()

  checks = [{ ...pending, status: 'COMPLETED', conclusion: 'SUCCESS' }, { __typename: 'StatusContext', context: 'jenkins', state: 'SUCCESS' }]
  await $.turn.complete({ turnId: 't2', answer: 'done', durationMs: 1, isAborted: false, reason: 'answer' })
  expect(toasts).toEqual(['PR #72: CI failing (python)', 'PR #72: CI green'])
})

test('past the compact threshold the band suggests /compact once and its button compacts', async ($, on) => {
  engine(on, {})
  const toasts: string[] = []
  let compactions = 0
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('session.compact', () => {
    compactions += 1
    return { messages: [{ role: 'user', text: 'summary', toolUses: [] }] } as never
  })
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'terminal', isInteractive: true })
  const at = (tokens: number) => ({ context: { tokens, window: 1_000_000, percent: tokens / 10_000 }, rateLimits: [], changed: ['context' as const] })
  for (const tokens of [200_000, 260_000, 300_000]) await $.session.measure(at(tokens))
  expect(toasts).toEqual(['Context at 260k tokens: a good point to /compact'])

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /consider/ }))?.text).toBe('context 300k: consider /compact ')
  await ui.press({ key: 'compact' })
  expect(compactions).toBe(1)
  await ui.unmount()
})
