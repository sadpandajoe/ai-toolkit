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

const engine = (on: On, env: Record<string, string>) => {
  const clock = mock.clock(on, { now: T0 })
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
  return clock
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

test('idle past the cache TTL is flagged', async ($, on) => {
  const clock = engine(on, {})
  on('turn.complete', (_, e) => ({ text: e.answer }))
  await $.session.start({ cwd: '/w/ai-toolkit', surface: 'desktop', isInteractive: true })
  await $.turn.complete({ turnId: 't1', answer: 'done', durationMs: 1000, isAborted: false, reason: 'answer' })
  await clock.advance(7 * 60_000)

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /^idle/ }))?.text).toBe('idle 7m · cache cold')
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
