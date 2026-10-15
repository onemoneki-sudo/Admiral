// Admiral's sidebar: the board `admiral board --write` leaves in <state_dir>/board.json every minute, drawn as a
// pane docked right of the transcript in every session. Its close mark (×) hides it; while hidden, one button above
// the prompt brings it back (/admiral toggles it too); the always-on summary is the status line
// (`admiral statusline`). Reads one local file every 10 seconds; calls no model and no GitHub. Every word it shows
// comes from the board's word table, in the language the config sets. It also ends every session's system prompt with
// the playbook's reminder (below), unless the config turns it off.
//
// Colors carry one meaning each: green is working or done, yellow is waiting for the person, red is broken
// (CI failed, data stale, a commander gone); everything else is gray.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Board, Group, Item, Row } from '../types'

const PANE = 'admiral'
const TITLE = 'Admiral'
const WIDTH = 50 // body columns asked for; the person's own drag wins
const REREAD_MS = 10_000
const STALE_S = 180 // board.json older than this means the launchd job stopped

// Skills are read when a session thinks of them; this names the moment for each, so the playbook holds in every
// session, not only in those that happen to open it. Written for the model, so in English whatever the language.
const PLAYBOOK = `# Admiral playbook

Several Claude Code sessions work on this machine in parallel, and the Admiral playbook says how they keep out of each other's way and deliver. Read each of its skills, with the Skill tool, before the moment it covers. Where the project's own rules say otherwise, the project's rules win.

- admiral:principles - before starting a task, before acting on a finding, before calling work done, and before writing a PR, issue or report.
- admiral:workspace - before working in a repository: the worktree, registration, what never to touch.
- admiral:pipeline - before a feature or fix (the task brief comes first), when development is done, before the full test gate and before pushing.
- admiral:roles - when named a commander, when given work large enough to split across sessions, and when dispatching or receiving work.
- admiral:resources - before heavy tests or anything else that needs a shared resource.
- admiral:wrapup - after a PR merges or closes, and when asked which sessions can be closed.`

const board = atom({ plugin: 'admiral', key: 'board' } as const, null)
const readError = atom({ plugin: 'admiral', key: 'readError' } as const, '')
const isCollapsed = atom({ plugin: 'admiral', key: 'isCollapsed' } as const, false)
const isHintsOpen = atom({ plugin: 'admiral', key: 'isHintsOpen' } as const, false)
const isIdleOpen = atom({ plugin: 'admiral', key: 'isIdleOpen' } as const, false)

const RUN: Record<string, { mark: string; color: string }> = {
  waiting: { mark: '◆', color: 'warning' },
  busy: { mark: '●', color: 'success' },
  shell: { mark: '◉', color: 'success' },
  idle: { mark: '○', color: 'inactive' },
}
const IDLE = { mark: '○', color: 'inactive' }

const BAR = 10

// A cell's green at `t` along the bar, 0 to 1: faint at the start, full green at the end, so the further a bar
// fills the greener its front.
// The green's ends come from the board (defined once in admiral/board.py).
let green = { faint: [52, 84, 64], full: [63, 185, 80] }
function shade(t: number): string {
  const { faint, full } = green
  return '#' + faint.map((a, i) => Math.round(a + ((full[i] ?? a) - a) * t).toString(16).padStart(2, '0')).join('')
}

// The board's word table, English until the first board is read.
type Words = Record<string, any>
let W: Words = {
  just_now: 'just now', now: 'working', short_min: '{n}m', short_h: '{n}h', short_d: '{n}d',
  min_ago: '{n} min ago', h_ago: '{n} h ago', d_ago: '{n} d ago', open_board: 'Admiral board',
  command_desc: 'Show or hide the Admiral board on the right', loading: "waiting for the background job's first refresh",
}
// "{n} {n:session|sessions}" picks the singular when n is 1, as admiral/words.py does.
const fmt = (key: string, vars: Record<string, string | number> = {}) =>
  String(W[key] ?? key)
    .replace(/\{(\w+):([^|{}]*)\|([^{}]*)\}/g, (_, k, one, many) => (String(vars[k]) === '1' ? one : many))
    .replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''))

function ago(nowS: number, t: number): string {
  if (!t) return ''
  const s = Math.max(0, nowS - t)
  if (s < 60) return fmt('just_now')
  if (s < 3600) return fmt('short_min', { n: Math.floor(s / 60) })
  if (s < 172800) return fmt('short_h', { n: Math.floor(s / 3600) })
  return fmt('short_d', { n: Math.floor(s / 86400) })
}

// When the session last did something: working while it works, else how long ago it stopped (or started waiting).
function lastActive(nowS: number, x: Row): string {
  if (x.status === 'busy' || x.status === 'shell') return fmt('now')
  const s = Math.max(0, nowS - x.statusSince)
  if (!x.statusSince) return ''
  if (s < 60) return fmt('just_now')
  if (s < 3600) return fmt('min_ago', { n: Math.floor(s / 60) })
  if (s < 172800) return fmt('h_ago', { n: Math.floor(s / 3600) })
  return fmt('d_ago', { n: Math.floor(s / 86400) })
}

function clock(t: number): string {
  const d = new Date(t * 1000)
  return [d.getHours(), d.getMinutes()].map(n => String(n).padStart(2, '0')).join(':')
}

function rowsOf(b: Board): Row[] {
  return [...b.groups.flatMap(g => (g.leadRow ? [g.leadRow, ...g.members] : g.members)), ...b.unassigned]
}

function tally(b: Board) {
  const rows = rowsOf(b)
  return {
    total: rows.length,
    waiting: rows.filter(x => x.status === 'waiting').length,
    busy: rows.filter(x => x.status === 'busy' || x.status === 'shell').length,
    ciFail: rows.filter(x => x.ciLevel === 'fail').length,
  }
}

// The `admiral` command: the clone's bin/admiral when the plugin is read from a clone (its real path resolves
// through a link), else `admiral` on the PATH. The state directory comes from `admiral where`, which honours the
// config; without an answer, the default.
let admiral = ''
let boardPath = ''

async function locate($: EngineInterface): Promise<void> {
  const real = (await $.fs.stat($.plugin.root, { resolve: true })).realPath ?? $.plugin.root
  const clone = `${real.replace(/\/plugin\/?$/, '')}/bin/admiral`
  admiral = (await $.fs.exists(clone)) ? clone : 'admiral'
  const where = await $.process.run([admiral, 'where'], { timeoutMs: 10_000 }).catch(() => null)
  let dir = where && where.exitCode === 0 ? where.stdout.trim() : ''
  if (!dir) {
    const home = await $.process.run(['/bin/sh', '-c', 'printf %s "$HOME"'], { timeoutMs: 5_000 })
    dir = `${home.stdout.trim()}/.local/state/admiral`
  }
  boardPath = `${dir}/board.json`
}

async function load($: EngineInterface): Promise<void> {
  let err = ''
  try {
    if (!boardPath) await locate($)
    const b = JSON.parse(await $.fs.read(boardPath)) as Board
    if (b.green) green = b.green
    if (b.words) W = b.words
    await update($, board, () => b)
  } catch (e) {
    err = `${boardPath || 'board.json'}: ${e instanceof Error ? e.message : String(e)}`
  }
  await update($, readError, () => err)
}

// The pane moves first and the atom after, so the button's redraw (it reads the atom) sees the pane's new state.
async function expand($: EngineInterface): Promise<boolean> {
  const opened = await $.ui.open({ id: PANE, title: TITLE, columns: WIDTH })
  await update($, isCollapsed, () => false)
  return opened.isPlaced
}

async function collapse($: EngineInterface): Promise<void> {
  await $.ui.close({ id: PANE })
  await update($, isCollapsed, () => true)
}

// Whether the pane is on screen now. Opened unasked it waits undrawn below 144 columns (110 once the person
// has opened it), so "not collapsed" is not "showing": the button and /admiral go by this.
async function isShowing($: EngineInterface): Promise<boolean> {
  return (await $.ui.panes()).some(p => p.id === PANE && p.isShown)
}

// Called from the person's press or command and awaited there, so the engine counts the open as theirs and
// places it at any width. A pane opened unasked on a narrow terminal stays open but undrawn; opening that id
// again only retitles it, so it is closed first and opened anew.
async function toggle($: EngineInterface): Promise<boolean> {
  const pane = (await $.ui.panes()).find(p => p.id === PANE)
  if (pane?.isShown) {
    await collapse($)
    return false
  }
  if (pane) await $.ui.close({ id: PANE })
  return expand($)
}

// A click on a conversation's name brings its terminal tab to the front (`admiral focus`: Terminal or iTerm2).
async function focus($: EngineInterface, x: Row): Promise<void> {
  if (!x.tty || !admiral) {
    $.ui.toast(fmt('no_terminal', { name: x.name }))
    return
  }
  const r = await $.process.run([admiral, 'focus', x.tty], { timeoutMs: 10_000 })
  if (r.exitCode !== 0) $.ui.toast(fmt('no_tab', { name: x.name, tty: x.tty }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await load($)
    await $.command.register({ name: 'admiral', description: fmt('command_desc') })
    $.clock.every(REREAD_MS, () => void load($))
    if (!(await read($, isCollapsed))) void expand($)

    return next(e)
  })

  // Last in the system prompt, after the cache boundary, only where the Skill tool is there to read the skills with.
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    if (!e.traits.includes('skills') || e.traits.includes('bare')) return composed
    if ((await read($, board))?.playbookReminder === false) return composed
    return { sections: [...composed.sections, { id: 'admiral:playbook', text: PLAYBOOK, scope: 'session' as const }] }
  })

  on('command.run', { command: 'admiral' }, async $ => {
    const wasShowing = await isShowing($)
    const isPlaced = await toggle($)
    if (wasShowing) return { text: fmt('pane_closed') }
    return { text: fmt(isPlaced ? 'pane_opened' : 'pane_waits') }
  })

  // The atom is written after the close has gone through, so the button's redraw finds the pane gone.
  on('ui.close', async ($, e, next) => {
    const closed = await next(e)
    if (e.id === PANE && e.origin.kind === 'person') await update($, isCollapsed, () => true)
    return closed
  })

  // Above the prompt, only while the pane is hidden: the button that brings it back. The engine offers no way
  // to reopen a closed pane, and closing is its own mark (×) on the pane, so nothing shows while it is open.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    await read($, isCollapsed) // redraw on show and hide
    if (e.props.hasSurvey || (await isShowing($))) return next(e)
    const { Box, Button } = $.ui.resolve(e)
    return (
      <Box justifyContent="flex-end">
        <Button key="toggle" label={`◂ ${fmt('open_board')}`} onPress={() => toggle($)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const b = await read($, board)
    const err = await read($, readError)
    const hintsOpen = await read($, isHintsOpen)
    const idleOpen = await read($, isIdleOpen)
    const nowS = (await $.clock.now()) / 1000
    const cols = Math.max(20, e.props.bodyColumns)
    const rule = (key: string) => <Text key={key} dimColor>{'─'.repeat(cols)}</Text>
    const sub = (key: string, text: string) => (
      <Box key={key} paddingLeft={2}>
        <Text dimColor>{text}</Text>
      </Box>
    )

    // HUD-style bar: filled cells in the green for its percentage, the rest dim; then the percentage and, once there
    // are PRs, how many merged.
    const bar = (p: number | null, merged: number, n: number) => {
      if (p === null) return <Text dimColor>{fmt('no_progress')}</Text>
      const filled = Math.round((BAR * p) / 100)
      return (
        <Box>
          {Array.from({ length: filled }, (_, i) => (
            <Text key={`c${i}`} color={shade((i + 1) / BAR)}>█</Text>
          ))}
          <Text dimColor>{'░'.repeat(BAR - filled)}</Text>
          <Text> {String(p).padStart(3)}%</Text>
          {n > 0 && <Text dimColor>  {fmt('prs_merged', { done: merged, n })}</Text>}
        </Box>
      )
    }

    // A conversation's or deliverable's milestone as five pips, deepening from faint to full green like the bar.
    const pips = (n: number) => (
      <Box marginLeft={1}>
        {Array.from({ length: n }, (_, i) => (
          <Text key={`p${i}`} color={shade((i + 1) / 5)}>▰</Text>
        ))}
        <Text dimColor>{'▱'.repeat(5 - n)}</Text>
      </Box>
    )

    // The line under a row, gray: owner and PR, only when there is one.
    const detail = (key: string, pr: string, owner = '') => {
      if (!pr && !owner) return null
      return (
        <Box key={key} paddingLeft={2}>
          <Text dimColor wrap="truncate-end">{[owner, pr].filter(Boolean).join(' · ')}</Text>
        </Box>
      )
    }

    // A failed CI is one red mark in a column of its own; which job failed is on the PR.
    const ciMark = (ciLevel: string) => (
      <Box width={2} justifyContent="flex-end">
        <Text color="error">{ciLevel === 'fail' ? '✗' : ' '}</Text>
      </Box>
    )

    // One conversation: its run mark, its name (yellow while it waits for the person), its stage, when it was
    // last active.
    const row = (x: Row, indent = 0) => {
      const run = RUN[x.status] ?? IDLE
      return (
        <Box key={`r-${x.name}`} flexDirection="column" paddingLeft={indent}>
          <Box>
            <Text color={run.color}>{run.mark} </Text>
            <Box flexGrow={1} flexShrink={1}>
              <Button key={`f-${x.name}`} label={x.name} plain dimColor={x.status === 'idle'} onPress={() => focus($, x)} />
            </Box>
            {x.stage ? pips(x.stage) : null}
            {ciMark(x.ciLevel)}
            <Box width={10} justifyContent="flex-end">
              <Text dimColor>{lastActive(nowS, x)}</Text>
            </Box>
          </Box>
          {detail(`d-${x.name}`, x.pr && x.pr.state === 'OPEN' ? x.pr.label : '')}
        </Box>
      )
    }

    // A planned deliverable: its owner's run mark, its title and stage; under it the owner, PR and failing CI.
    const deliverable = (it: Item, owner: Row | undefined) => {
      const run = owner ? RUN[owner.status] ?? IDLE : IDLE
      return (
        <Box key={`i-${it.branch}`} flexDirection="column" paddingLeft={1}>
          <Box>
            <Text color={run.color}>{run.mark} </Text>
            <Box flexGrow={1} flexShrink={1}>
              <Text wrap="truncate-end" dimColor={it.stage === 4}>{it.title || it.branch}</Text>
            </Box>
            {pips(it.stage)}
            {ciMark(it.ciLevel)}
            <Box width={10} justifyContent="flex-end">
              <Text dimColor>{owner ? lastActive(nowS, owner) : ''}</Text>
            </Box>
          </Box>
          {detail(`d-${it.branch}`, it.pr?.label ?? '', it.owner || fmt('no_owner'))}
        </Box>
      )
    }

    // A commander: its name and own state, where its work stands (its plan's deliverables, or its live members
    // when it has no plan), then its deliverables and, under them, the sessions that own none.
    const team = (g: Group) => {
      const s = g.summary
      const own = g.leadRow ? RUN[g.leadRow.status] ?? IDLE : { mark: '✗', color: 'error' }
      const loose = g.batch ? g.members.filter(m => !g.batch!.items.some(it => it.owner === m.name)) : g.members
      return (
        <Box key={`g-${g.lead}`} flexDirection="column" marginTop={1}>
          <Box>
            <Text color={own.color}>{own.mark} </Text>
            <Box flexGrow={1} flexShrink={1}>
              {g.leadRow ? (
                <Button key={`f-${g.lead}`} label={g.lead} plain onPress={() => focus($, g.leadRow!)} />
              ) : (
                <Text bold wrap="truncate-end">{g.lead}</Text>
              )}
            </Box>
            {g.leadRow ? <Text dimColor>{lastActive(nowS, g.leadRow)}</Text> : <Text color="error">{fmt('not_running')}</Text>}
          </Box>
          <Box paddingLeft={2}>
            {bar(s.pct, s.prsMerged ?? 0, s.prs ?? 0)}
            {g.batch ? null : <Text dimColor>  {fmt('no_plan')}</Text>}
          </Box>
          {g.batch ? sub(`s-i-${g.lead}`, fmt('deliverables')) : null}
          {g.batch ? g.batch.items.map(it => deliverable(it, g.members.find(m => m.name === it.owner))) : null}
          {g.batch && loose.length ? sub(`s-r-${g.lead}`, fmt('other_sessions')) : null}
          {loose.map(x => row(x, g.batch ? 1 : 0))}
        </Box>
      )
    }

    const t = b ? tally(b) : null
    const parts = [
      // the engine draws its own close mark (×) on the pane's frame, so the head has no button of its own
      <Box key="head">
        <Text bold color="claude">Admiral</Text>
        <Text dimColor>{b ? `  ${fmt('updated', { t: clock(b.generated) })}` : ''}</Text>
      </Box>,
    ]
    if (b && b.dist.some(Boolean)) {
      parts.push(
        <Box key="overall">
          <Text dimColor>{fmt('overall')} </Text>
          {bar(b.pct, b.prsMerged ?? 0, b.prs ?? 0)}
        </Box>,
      )
    }
    if (t) {
      parts.push(
        <Box key="counts">
          <Text dimColor>{fmt('total', { n: t.total })} </Text>
          <Text color={t.waiting ? 'warning' : 'inactive'}>◆ {t.waiting} {fmt('waiting')}  </Text>
          <Text color={t.busy ? 'success' : 'inactive'}>● {t.busy} {fmt('working')}  </Text>
          <Text color="inactive">○ {t.total - t.waiting - t.busy} {fmt('idle')}  </Text>
          <Text color={t.ciFail ? 'error' : 'inactive'}>✗</Text>
          <Text color="inactive"> {t.ciFail} {fmt('ci')}</Text>
        </Box>,
      )
    }
    for (const [i, h] of (b?.health ?? []).entries()) {
      parts.push(<Text key={`health-${i}`} color="error" wrap="wrap">⚠ {h}</Text>)
    }
    if (!b || err || nowS - b.generated > STALE_S) {
      const why = err || (b ? fmt('stale', { age: ago(nowS, b.generated) }) : fmt('loading'))
      parts.push(<Text key="stale" color="error">{why}</Text>)
    }
    if (!b) return <Box flexDirection="column">{parts}</Box>

    parts.push(rule('r-top'))
    if (b.waiting.length) {
      parts.push(
        <Box key="waiting" flexDirection="column" borderStyle="round" borderColor="warning" paddingX={1}>
          <Text color="warning" bold>{fmt('waiting')}</Text>
          {b.waiting.map(x => (
            <Box key={`w-${x.name}`} flexDirection="column">
              <Box>
                <Text color="warning">◆ </Text>
                <Box flexGrow={1} flexShrink={1}>
                  <Button key={`fw-${x.name}`} label={x.name} plain onPress={() => focus($, x)} />
                </Box>
                <Text dimColor>{ago(nowS, x.statusSince)}</Text>
              </Box>
              {x.waitingFor ? (
                <Box paddingLeft={2}>
                  <Text dimColor wrap="truncate-end">
                    {(x.waitKind === 'maybe' ? fmt('maybe_waiting') : x.waitKind === 'reported' ? fmt('reported_waiting') : '') + x.waitingFor}
                  </Text>
                </Box>
              ) : null}
            </Box>
          ))}
        </Box>,
      )
    }

    b.groups.filter(g => g.summary.total > 0 || g.batch).forEach(g => parts.push(team(g)))

    // commanders with neither members nor a plan: one line, opened on demand
    const idle = b.groups.filter(g => g.summary.total === 0 && !g.batch && g.leadRow)
    if (idle.length) {
      parts.push(
        <Box key="idle-head" marginTop={1}>
          <Box flexGrow={1}>
            <Text dimColor>{fmt('idle_commanders', { n: idle.length })}</Text>
          </Box>
          <Button key="idle" label={fmt(idleOpen ? 'hide' : 'show')} onPress={() => update($, isIdleOpen, v => !v)} />
        </Box>,
      )
      if (idleOpen) idle.forEach(g => parts.push(row(g.leadRow!, 1)))
    }

    if (b.unassigned.length) {
      parts.push(
        <Box key="u-head" marginTop={1}>
          <Text bold>{fmt('independent')}</Text>
          <Text dimColor>  {b.unassigned.length}</Text>
        </Box>,
      )
      b.unassigned.forEach(x => parts.push(row(x)))
    }

    // Which sessions can be closed (wrap up after the PR merged, then close); names focus them.
    const close = b.closable
    const closeRows: [string, string, { name: string; lead: string; tty: string; why: string }[]][] = [
      [fmt('can_close'), 'success', close?.close ?? []],
      [fmt('wrap_up'), 'text', close?.wrapup ?? []],
      [fmt('confirm'), 'warning', close?.confirm ?? []],
    ]
    if (closeRows.some(([, , xs]) => xs.length)) {
      parts.push(rule('r-close'))
      parts.push(<Text key="close-head" bold>{fmt('close_head')}</Text>)
      for (const [title, color, xs] of closeRows) {
        if (!xs.length) continue
        parts.push(<Text key={`ch-${title}`} color={color} dimColor={color === 'text'}>{title} {xs.length}</Text>)
        xs.forEach(x => {
          const row = rowsOf(b).find(r => r.name === x.name)
          parts.push(
            <Box key={`c-${title}-${x.name}`} flexDirection="column" paddingLeft={1}>
              <Button key={`fc-${x.name}`} label={x.name} plain onPress={() => (row ? focus($, row) : undefined)} />
              <Box paddingLeft={2}>
                <Text dimColor wrap="truncate-end">{x.why}</Text>
              </Box>
            </Box>,
          )
        })
      }
    }

    if (b.hints.length) {
      parts.push(rule('r-hints'))
      parts.push(
        <Box key="hints-head">
          <Box flexGrow={1}>
            <Text dimColor>{fmt('to_tidy', { n: b.hints.length })}</Text>
          </Box>
          <Button key="hints" label={fmt(hintsOpen ? 'hide' : 'show')} onPress={() => update($, isHintsOpen, v => !v)} />
        </Box>,
      )
      if (hintsOpen) {
        b.hints.forEach((hint, i) => parts.push(<Text key={`h-${i}`} dimColor wrap="truncate-end">· {hint}</Text>))
      }
    }

    return <Box flexDirection="column">{parts}</Box>
  })
}
