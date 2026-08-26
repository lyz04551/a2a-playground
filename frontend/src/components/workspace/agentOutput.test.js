import assert from 'node:assert/strict'
import test from 'node:test'
import { formatAgentOutput } from './agentOutput.js'

test('shows the summary from a structured Agent JSON string', () => {
  const value = JSON.stringify({
    status: 'completed',
    summary: '安全检查通过，可以继续部署。',
    findings: [],
  })

  assert.equal(formatAgentOutput(value), '安全检查通过，可以继续部署。')
})

test('shows the summary from an Agent result object', () => {
  assert.equal(formatAgentOutput({ status: 'completed', summary: 'Pod 运行正常。' }), 'Pod 运行正常。')
})

test('keeps ordinary text and malformed JSON readable', () => {
  assert.equal(formatAgentOutput('部署已经完成。'), '部署已经完成。')
  assert.equal(formatAgentOutput('{not-json}'), '{not-json}')
})
