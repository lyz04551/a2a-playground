import test from 'node:test'
import assert from 'node:assert/strict'
import { approvalRisk, diffArguments, formatArgumentValue, redactSensitive } from './operationSafety.js'

test('recursively redacts sensitive values without mutating input', () => {
  const input = { token: 'one', nested: { api_key: 'two', safe: 3 }, rows: [{ password: 'three' }] }
  assert.deepEqual(redactSensitive(input), { token: '[REDACTED]', nested: { api_key: '[REDACTED]', safe: 3 }, rows: [{ password: '[REDACTED]' }] })
  assert.equal(input.token, 'one')
})

test('approval argument diff reports added removed and changed paths', () => {
  assert.deepEqual(diffArguments({ namespace: 'a', replicas: 1, old: true }, { namespace: 'a', replicas: 2, image: 'v2' }), [
    { path: 'image', kind: 'added', before: undefined, after: 'v2' },
    { path: 'old', kind: 'removed', before: true, after: undefined },
    { path: 'replicas', kind: 'changed', before: 1, after: 2 },
  ])
})

test('formats multiline manifest values without escaped newline sequences', () => {
  const manifest = 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: nginx'

  assert.equal(formatArgumentValue(manifest), manifest)
  assert.equal(formatArgumentValue({ image: 'nginx:1.25' }), '{\n  "image": "nginx:1.25"\n}')
  assert.equal(formatArgumentValue(undefined), '—')
})

test('approval risk respects explicit values and detects destructive tools', () => {
  assert.equal(approvalRisk({ risk_level: 'high' }), 'high')
  assert.equal(approvalRisk({ tool_name: 'delete_workload' }), 'critical')
  assert.equal(approvalRisk({ tool_name: 'scale_workload' }), 'write')
})
