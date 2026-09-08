import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('task explorer columns and payloads stay bounded', () => {
  const css = readFileSync(new URL('../styles/tasks.css', import.meta.url), 'utf8')
  assert.match(css, /grid-template-columns:\s*minmax\(220px,\s*300px\)\s+minmax\(0,\s*1fr\)/)
  assert.match(css, /\.task-explorer__flow[^}]*overflow-y:\s*auto/s)
  assert.match(css, /\.task-node-drawer pre[^}]*overflow-wrap:\s*anywhere/s)
  assert.match(css, /@media\s*\(max-width:\s*820px\)/)
})
