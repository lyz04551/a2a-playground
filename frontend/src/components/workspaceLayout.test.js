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

test('approval argument diff stays bounded and readable in the narrow trace column', () => {
  const css = readFileSync(new URL('../styles/workspace.css', import.meta.url), 'utf8')
  const listRule = css.match(/\.approval-card__diff-list\s*\{([^}]+)\}/)?.[1] || ''
  const rowRule = css.match(/\.approval-card__diff li\s*\{([^}]+)\}/)?.[1] || ''
  const valueRule = css.match(/\.approval-card__diff-value\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(listRule, /max-height:\s*min\(/)
  assert.match(listRule, /overflow-y:\s*auto/)
  assert.match(rowRule, /grid-template-columns:\s*minmax\(64px,\s*\.32fr\)\s+minmax\(0,\s*1fr\)/)
  assert.match(valueRule, /min-width:\s*0/)
  assert.match(valueRule, /overflow-wrap:\s*anywhere/)
  assert.match(valueRule, /white-space:\s*pre-wrap/)
})

test('pending approval actions remain visible without covering diff content', () => {
  const css = readFileSync(new URL('../styles/workspace.css', import.meta.url), 'utf8')
  const cardRule = css.match(/\.approval-card\s*\{([^}]+)\}/)?.[1] || ''
  const actionsRule = css.match(/\.approval-card__actions\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(cardRule, /min-width:\s*0/)
  assert.match(actionsRule, /position:\s*sticky/)
  assert.match(actionsRule, /bottom:\s*0/)
})

test('long agent messages scroll internally without widening the conversation', () => {
  const css = readFileSync(new URL('../styles/workspace.css', import.meta.url), 'utf8')
  const messageRule = css.match(/\.workspace-message--agent \.workspace-message__body\s*\{([^}]+)\}/)?.[1] || ''

  assert.match(messageRule, /max-height:\s*min\(/)
  assert.match(messageRule, /overflow-y:\s*auto/)
  assert.match(messageRule, /overflow-x:\s*hidden/)
  assert.match(messageRule, /overflow-wrap:\s*anywhere/)
})
