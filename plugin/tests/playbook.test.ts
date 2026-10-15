import { expect, test } from 'claude-code/testing'

// The engine's own sections, and the facts a system prompt is composed from, with the traits under test.
const base = { sections: [{ id: 'intro', text: 'engine', scope: 'shared' as const }] }
const facts = (traits: string[]) => ({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits }) as any

test('the reminder goes last where the Skill tool lists skills', async ($, on) => {
  on('prompt.compose', async () => base)
  const r = await $.prompt.compose(facts(['skills']))
  expect(r.sections.map(s => s.id)).toEqual(['intro', 'admiral:playbook'])
  expect(r.sections[1]!.scope).toBe('session')
  expect(r.sections[1]!.text).toContain('admiral:pipeline')
})

test('no reminder without the Skill tool, or in a bare session', async ($, on) => {
  on('prompt.compose', async () => base)
  expect((await $.prompt.compose(facts([]))).sections.map(s => s.id)).toEqual(['intro'])
  expect((await $.prompt.compose(facts(['skills', 'bare']))).sections.map(s => s.id)).toEqual(['intro'])
})
