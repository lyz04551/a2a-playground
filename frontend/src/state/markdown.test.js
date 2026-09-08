import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeMarkdown } from './markdown.js'

test('normalizes transport-escaped Markdown punctuation', () => {
  assert.equal(normalizeMarkdown('\\## 标题\n\\*\\*重点\\*\\*\n\\| A \\| B \\|'), '## 标题\n**重点**\n| A | B |')
})

test('preserves newlines and ordinary backslashes', () => {
  assert.equal(normalizeMarkdown('line 1\nC:\\temp\\file'), 'line 1\nC:\\temp\\file')
})
