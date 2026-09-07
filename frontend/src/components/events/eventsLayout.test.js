import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('tool payloads stay readable and bounded at narrow widths', () => {
  const css = readFileSync(new URL('../../styles/events.css', import.meta.url), 'utf8')
  const rule = css.match(/\.event-payload-json\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(rule, /max-width:\s*100%/)
  assert.match(rule, /max-height:\s*min\(/)
  assert.match(rule, /overflow-x:\s*hidden/)
  assert.match(rule, /overflow-y:\s*auto/)
  assert.match(rule, /white-space:\s*pre-wrap/)
  assert.match(rule, /overflow-wrap:\s*anywhere/)
})
