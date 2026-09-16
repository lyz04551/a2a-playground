import test from 'node:test'
import assert from 'node:assert/strict'

import { diagnosticView } from './connectionDiagnostics.js'


test('connection diagnostics map independent probe states to readable UI states', () => {
  assert.deepEqual(diagnosticView({ state: 'ok', latency_ms: 12 }), {
    label: '正常', color: 'success', latency: '12 ms', error: '',
  })
  assert.equal(diagnosticView({ state: 'error', error: 'timeout' }).color, 'error')
  assert.equal(diagnosticView({ state: 'offline' }).label, '离线')
  assert.equal(diagnosticView({ state: 'unsupported' }).label, '不支持')
  assert.equal(diagnosticView(null).label, '未测试')
})
