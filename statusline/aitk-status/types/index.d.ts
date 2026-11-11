
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

/** The branch's pull request and its checks, from `gh pr view`. */
export type Pr = {
  number: number
  url: string
  /** OPEN, MERGED or CLOSED. */
  state: string
  isDraft: boolean
  passed: number
  pending: number
  /** Names of the failed checks (Actions runs and external status contexts). */
  failing: string[]
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
      /** Share of the last main-loop turn's input tokens read from the prompt cache, 0 to 100. */
      cacheHit: number | null
      /** Limit warnings already toasted, as `kind@resetsAt@level`, so each fires once per window. */
      toasted: Shaped<string[]>
      pr: Shaped<Pr | null>
      /** Tokens each main-loop prompt used (input, cache and output), oldest first. */
      perPrompt: Shaped<number[]>
      /** Prompt-cache TTL in minutes: learned from a turn after an idle gap, else 5. */
      cacheTtl: number
      /** Whether the TTL was learned rather than assumed. */
      isTtlLearned: boolean
      /** Whether the compact suggestion has toasted since the context last grew past it. */
      compactToasted: boolean
    }
  }
}
