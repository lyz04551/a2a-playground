import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('desktop trace column remains a bounded vertical scroll container', () => {
  const css = readFileSync(new URL('../styles/workspace.css', import.meta.url), 'utf8')
  const rule = css.match(/\.agent-workspace__trace\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(rule, /min-height:\s*0/)
  assert.match(rule, /height:\s*100%/)
  assert.match(rule, /overflow-y:\s*auto/)
})
