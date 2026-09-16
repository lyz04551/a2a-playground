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

test('long inline code wraps without changing fenced code block scrolling', () => {
  const css = fs.readFileSync(new URL('../styles/markdown.css', import.meta.url), 'utf8')
  const rootRule = css.match(/\.markdown-content\s*\{([^}]+)\}/)?.[1] || ''
  const inlineCodeRule = css.match(/\.markdown-content code\s*\{([^}]+)\}/)?.[1] || ''
  const fencedCodeRule = css.match(/\.markdown-content pre code\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(rootRule, /max-width:\s*100%/)
  assert.match(inlineCodeRule, /white-space:\s*normal/)
  assert.match(inlineCodeRule, /overflow-wrap:\s*anywhere/)
  assert.match(inlineCodeRule, /word-break:\s*break-word/)
  assert.match(fencedCodeRule, /white-space:\s*inherit/)
})
