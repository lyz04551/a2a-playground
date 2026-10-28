import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeMarkdown, normalizeReportHeadings } from './markdown.js'

test('normalizes transport-escaped Markdown punctuation', () => {
  assert.equal(normalizeMarkdown('\\## 标题\n\\*\\*重点\\*\\*\n\\| A \\| B \\|'), '## 标题\n**重点**\n| A | B |')
})

test('preserves newlines and ordinary backslashes', () => {
  assert.equal(normalizeMarkdown('line 1\nC:\\temp\\file'), 'line 1\nC:\\temp\\file')
})

test('promotes a report starting at heading level three to the standard report hierarchy', () => {
  assert.equal(
    normalizeReportHeadings('### 检查报告\n\n#### 已枚举资源\n正文\n##### 细节'),
    '# 检查报告\n\n## 已枚举资源\n正文\n### 细节',
  )
  assert.equal(normalizeReportHeadings('# 检查报告\n## 已枚举资源'), '# 检查报告\n## 已枚举资源')
})

test('leaves fenced code and non-heading text untouched when normalizing report headings', () => {
  assert.equal(
    normalizeReportHeadings('```md\n### 示例\n```\n### 检查报告\n\n    #### 不是标题'),
    '```md\n### 示例\n```\n# 检查报告\n\n    #### 不是标题',
  )
})
