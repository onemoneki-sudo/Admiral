export type Row = {
  name: string
  sessionId: string
  tty: string
  done: boolean
  stage: number
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
}

export type Item = {
  branch: string
  title: string
  owner: string
  stage: number
  pr: { number: number; state: string; label: string } | null
  ci: string
  ciLevel: 'ok' | 'run' | 'fail' | 'none'
}

export type Group = {
  lead: string
  leadRow: Row | null
  members: Row[]
  batch?: { items: Item[] }
  summary: { total: number; done: number; dist: number[]; pct: number | null; prs?: number; prsMerged?: number; progressFrom: string; items: number; itemsDone: number; busy: number; waiting: number; ciFail: number }
}

export type Board = {
  generated: number
  dist: number[]
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
  mine?: { open: number; mergedToday: number } | null
  closable?: Record<'close' | 'wrapup' | 'confirm', { name: string; lead: string; tty: string; why: string }[]>
}

declare module 'claude-code' {
  interface PluginState {
    'admiral': { board: Board | null; readError: string; isCollapsed: boolean; isHintsOpen: boolean; isIdleOpen: boolean }
  }
}
