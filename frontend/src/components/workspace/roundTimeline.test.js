import test from 'node:test'
import assert from 'node:assert/strict'
import { buildRoundTimeline, roundDisplayText } from './roundTimeline.js'

test('shows live analysis text before a Host decision is available', () => {
  assert.equal(roundDisplayText({ status: 'working' }, true), '正在分析下一步…')
  assert.equal(roundDisplayText({ status: 'working' }, false), 'Analyzing the next step…')
  assert.equal(roundDisplayText({ status: 'completed', reason: '需要验证 Pod' }, true), '需要验证 Pod')
})

test('groups parallel tasks under their react decision and appends later rounds', () => {
  const items = buildRoundTimeline(
    [
      { id: 'security', round: 1 },
      { id: 'capacity', round: 1 },
      { id: 'orchestrator', round: 2 },
    ],
    [
      { round: 1, reason: 'parallel checks', taskIds: ['security', 'capacity'] },
      { round: 2, reason: 'create resource', taskIds: ['orchestrator'] },
    ],
  )

  assert.deepEqual(items.map(item => `${item.kind}:${item.id}`), [
    'decision:round-1',
    'task:security',
    'task:capacity',
    'decision:round-2',
    'task:orchestrator',
  ])
})

test('keeps legacy tasks visible when no react rounds exist', () => {
  assert.deepEqual(
    buildRoundTimeline([{ id: 'legacy' }], []),
    [{ kind: 'task', id: 'legacy', task: { id: 'legacy' } }],
  )
})
