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

test('hides coverage JSON embedded in a report', () => {
  const report = '检查完成。\n```json\n{"scope":"cluster","expected_targets":["default"],"inspected_targets":["default/pod"],"enumeration_complete":true,"evidence_call_ids":["list_k8s_event_default"]}\n```'
  assert.equal(formatAgentOutput(report), '检查完成。')
  assert.equal(formatAgentOutput('检查完成。\n```json\n{"scope":'), '检查完成。')
  assert.equal(formatAgentOutput('检查完成。\n{"scope":'), '检查完成。')
})
