import fs from 'node:fs'
import test from 'node:test'
import assert from 'node:assert/strict'

test('Markdown tables fit messages and scroll only inside narrow containers', () => {
  const css = fs.readFileSync(new URL('../styles/markdown.css', import.meta.url), 'utf8')
  assert.match(css, /\.markdown-content__table[^}]*overflow-x:\s*auto/s)
  assert.match(css, /\.markdown-content table[^}]*width:\s*100%/s)
  assert.match(css, /\.markdown-content th[^}]*overflow-wrap:\s*anywhere/s)
  assert.match(css, /\.markdown-content\.is-compact[^}]*font-size/s)
})
