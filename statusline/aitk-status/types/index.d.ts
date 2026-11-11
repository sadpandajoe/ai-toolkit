
/** The status figures the engine measures (`session.measure`). */
export type Usage = {
  startedAt: number
  /** Input tokens of the last response; absent before the first. */
  tokens?: number
  window: number
  percent?: number
  costUsd?: number
  limits: { kind: string; percentUsed: number; resetsAt?: string }[]
}

/** The working tree, read with git after each turn. */
export type Git = {
  branch: string
  repo: string
  /** https URL of `origin`, when it is one. */
  web?: string
  /** Staged, unstaged and untracked paths. */
  changes: number
}

/** The main loop's last model request. */
export type Step = { model: string; effort?: string }

declare module 'claude-code' {
  interface PluginState {
    'aitk-status': {
      usage: Shaped<Usage | null>
      git: Shaped<Git | null>
      step: Shaped<Step | null>
      /** `$.clock.now()` when the last turn ended; null while one runs. */
      idleSince: number | null
      /** The minute clock the idle figure is drawn from. */
      now: number
      /** `AITK_PR_READY` and `SKIP_PRECHECK` as the session started with them. */
      overrides: Shaped<string[]>
    }
  }
}
