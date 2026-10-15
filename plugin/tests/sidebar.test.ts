import { expect, test } from 'claude-code/testing'

// The sidebar drawn from a board with one commander's plan: what the engine would answer beneath the plugin (the
// state directory, the board file, the clock, the pane) is answered here.

const now = Math.floor(Date.now() / 1000)
const row = (name: string, status: string, tty: string) => ({
  name, sessionId: name, tty, done: false, stage: 2, leadFrom: 'registration', lead: 'Commander-Mail', status, run: status,
  statusSince: now - 60, waitingFor: '', registered: true, phase: 'working', note: '', pr: null, ci: '', ciLevel: 'none' })
const owner = row('Fix-Mail', 'busy', 'ttys042')
const board = {
  generated: now, dist: [0, 1, 0, 0, 0, 0], pct: 50, count: 2, waiting: [], unassigned: [], hints: [], health: [],
  words: {}, closable: { close: [], wrapup: [], confirm: [] },
  groups: [{
    lead: 'Commander-Mail', leadRow: row('Commander-Mail', 'idle', 'ttys041'), members: [owner],
    batch: { items: [
      { branch: 'fix/mail', title: 'Send mail with CRLF line endings', owner: 'Fix-Mail', stage: 2,
        pr: { number: 12, state: 'OPEN', label: '#12 in review' }, ci: '', ciLevel: 'none' },
      { branch: 'fix/gone', title: 'A PR whose session closed', owner: 'Gone', stage: 1, pr: null, ci: '', ciLevel: 'none' }] },
    summary: { total: 2, done: 0, dist: [0, 1, 0, 0, 0, 0], pct: 50, prs: 1, prsMerged: 0, progressFrom: 'plan', items: 2, itemsDone: 0, busy: 1, waiting: 0, ciFail: 0 },
  }],
}

test('a planned PR is led by its owner, and a click brings the owner forward', async ($, on) => {
  const runs: string[][] = []
  on('session.start', async (_$, e: any) => ({ cwd: e.cwd }) as any)
  on('fs.stat', async () => ({ value: { realPath: '/opt/admiral-cache/plugin', isFile: false, isDirectory: true, size: 0, mtimeMs: 0 } }) as any)
  on('fs.exists', async () => ({ value: false }) as any)
  on('process.run', async (_$, e: any) => {
    runs.push(e)
    return { value: { exitCode: 0, stdout: '/state\n', stderr: '' } } as any
  })
  on('fs.read', async () => ({ value: JSON.stringify(board) }) as any)
  on('command.register', async () => ({ value: undefined }) as any)
  on('clock.every', async () => ({ value: undefined }) as any)
  on('ui.open', async () => ({ value: { isPlaced: true } }) as any)
  on('clock.now', async () => ({ value: Date.now() }) as any)
  on('ui.panes', async () => ({ value: [] }) as any)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as any)
  const ui = await $.ui.mount({ plugin: 'admiral', surface: 'terminal', component: 'Pane', requestId: 'admiral',
    props: { title: 'Admiral', isFocused: true, bodyColumns: 50, placement: 'dock' } as any })
  const shown = JSON.stringify(await (ui as any).findAll({}))
  expect(shown).toContain('Fix-Mail')
  expect(shown).toContain('Send mail with CRLF')
  expect(shown).toContain('A PR whose session closed')
  await (ui as any).press({ key: 'fo-fix/mail' })
  expect(JSON.stringify(runs.at(-1))).toContain('ttys042')
})
