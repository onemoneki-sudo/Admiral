export type Row = {
  name: string
  sessionId: string
  tty: string
  done: boolean
  stage: number  // on the scale before check had a milestone (0 to 5), for sidebars from before
  milestone?: number  // 0 to 6, from the boards that have check
  reportedDone?: boolean
  leadFrom: string
  lead: string
  status: string
  run: string
  statusSince: number
  waitingFor: string
  waitKind?: string
  registered: boolean
  phase: string | null
  note: string
  pr: { number: number; state: string; label: string } | null
  ci: string
  ciLevel: 'ok' | 'run' | 'fail' | 'none'
  agent?: 'claude' | 'codex'
}

export type Item = {
  branch: string
  title: string
  owner: string
  stage: number
  milestone?: number
  reportedDone?: boolean
  pr: { number: number; state: string; label: string } | null
  ci: string
  ciLevel: 'ok' | 'run' | 'fail' | 'none'
}

export type Group = {
  lead: string
  leadRow: Row | null
  members: Row[]
  batch?: { items: Item[] }
  summary: { total: number; done: number; dist: number[]; milestones?: number[]; pct: number | null; reported?: number; prs?: number; prsMerged?: number; progressFrom: string; items: number; itemsDone: number; busy: number; waiting: number; ciFail: number }
}

export type Board = {
  generated: number
  dist: number[]
  milestones?: number[]
  pct: number | null
  prs?: number
  prsMerged?: number
  count: number
  waiting: Row[]
  groups: Group[]
  unassigned: Row[]
  hints: string[]
  health?: string[]
  green?: { faint: number[]; full: number[] }
  words: Record<string, string | string[] | Record<string, string>>
  language?: string
  playbookReminder?: boolean
  mine?: { open: number; mergedToday: number } | null
  closable?: Record<'close' | 'wrapup' | 'confirm', { name: string; lead: string; tty: string; why: string }[]>
}

declare module 'claude-code' {
  interface PluginState {
    'admiral': { board: Board | null; readError: string; isCollapsed: boolean; isHintsOpen: boolean; isIdleOpen: boolean
      refreshBegan: number }
  }
}
