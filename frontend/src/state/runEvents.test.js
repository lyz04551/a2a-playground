import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyRunState, normalizeLegacyRunEvent, reduceRunEvent } from './runEvents.js'

function event(type, sequence, data = {}, overrides = {}) {
  return {
    version: 1,
    event_id: `evt-${sequence}`,
    sequence,
    run_id: 'run-1',
    conversation_id: 'conversation-1',
    task_id: 'task-1',
    parent_task_id: null,
    type,
    timestamp: '2026-07-30T12:00:00Z',
    data,
    ...overrides,
  }
}

test('run lifecycle and task events reduce into normalized run and ordered task state', () => {
  let state = reduceRunEvent(emptyRunState, event('run.started', 1, { mode: 'auto' }))
  state = reduceRunEvent(state, event('task.delegated', 2, { agent_id: 'ops', label: 'Inspect cluster' }, { task_id: 'task-ops' }))
  state = reduceRunEvent(state, event('task.completed', 3, { result: 'healthy' }, { task_id: 'task-ops' }))

  assert.equal(state.run.status, 'running')
  assert.deepEqual(state.taskOrder, ['task-ops'])
  assert.deepEqual(state.tasksById['task-ops'], {
    id: 'task-ops', parentTaskId: null, agentId: 'ops', label: 'Inspect cluster', status: 'completed', completedAt: '2026-07-30T12:00:00.000Z', result: 'healthy',
  })
  assert.equal(state.lastSequence, 3)
})

test('message, approval, artifact, and terminal events update their normalized collections', () => {
  let state = reduceRunEvent(emptyRunState, event('run.started', 1))
  state = reduceRunEvent(state, event('message.delta', 2, { content: 'Hel', role: 'agent', message_id: 'msg-1' }))
  state = reduceRunEvent(state, event('message.completed', 3, { content: 'Hello', role: 'agent', message_id: 'msg-1' }))
  state = reduceRunEvent(state, event('approval.required', 4, { id: 'approval-1', tool_name: 'apply' }))
  state = reduceRunEvent(state, event('artifact.created', 5, { id: 'artifact-1', name: 'plan.yaml' }))
  state = reduceRunEvent(state, event('run.completed', 6))

  assert.deepEqual(state.messages, [{ id: 'msg-1', role: 'agent', content: 'Hello', taskId: 'task-1', completed: true }])
  assert.equal(state.approvals[0].id, 'approval-1')
  assert.equal(state.artifacts[0].name, 'plan.yaml')
  assert.equal(state.run.status, 'completed')
})

test('duplicate envelopes leave normalized state unchanged', () => {
  const started = event('run.started', 1)
  const once = reduceRunEvent(emptyRunState, started)
  const twice = reduceRunEvent(once, started)

  assert.strictEqual(twice, once)
})

test('status events retain task metadata when they omit it', () => {
  let state = reduceRunEvent(emptyRunState, event('task.delegated', 1, {
    agent_id: 'ops', label: 'Inspect cluster',
  }))
  state = reduceRunEvent(state, event('task.started', 2, {}))
  state = reduceRunEvent(state, event('task.status_changed', 3, { state: 'waiting' }))

  assert.equal(state.tasksById['task-1'].agentId, 'ops')
  assert.equal(state.tasksById['task-1'].label, 'Inspect cluster')
  assert.equal(state.tasksById['task-1'].status, 'waiting')
})

test('legacy events are normalized at one adapter boundary', () => {
  assert.deepEqual(normalizeLegacyRunEvent({
    type: 'tool_call', id: 'call-1', tool: 'kubectl_get', args: { pod: 'api' },
  }), {
    version: 1,
    event_id: 'legacy:tool.called:call-1',
    sequence: 0,
    run_id: 'legacy',
    conversation_id: 'legacy',
    task_id: 'call-1',
    parent_task_id: null,
    type: 'tool.called',
    timestamp: '',
    data: { id: 'call-1', tool: 'kubectl_get', arguments: { pod: 'api' } },
  })
})

test('legacy callers retain their status and trace view during migration', () => {
  let state = reduceRunEvent(emptyRunState, { type: 'run_started' })
  state = reduceRunEvent(state, { type: 'tool_call', id: 'call-1', tool: 'kubectl_get' })
  state = reduceRunEvent(state, { type: 'tool_result', id: 'call-1', result: 'ready' })

  assert.equal(state.status, 'running')
  assert.deepEqual(state.steps, [{
    id: 'call-1', kind: 'tool', label: 'kubectl_get', arguments: {}, status: 'completed', result: 'ready',
  }])
})

test('retains raw events in sequence order with normalized timestamps', () => {
  let state = reduceRunEvent(emptyRunState, event('run.started', 2, {}, { timestamp: '2026-07-30T12:00:02Z' }))
  state = reduceRunEvent(state, event('host.planning', 1, {}, { timestamp: '2026-07-30T12:00:01Z' }))

  assert.deepEqual(state.rawEvents.map(item => item.sequence), [1, 2])
  assert.equal(state.rawEvents[0].timestamp, '2026-07-30T12:00:01.000Z')
})

test('derives task duration from real start and completion timestamps', () => {
  let state = reduceRunEvent(emptyRunState, event('task.started', 1, {}, { timestamp: '2026-07-30T12:00:00Z' }))
  state = reduceRunEvent(state, event('task.completed', 2, { result: 'ok' }, { timestamp: '2026-07-30T12:00:02.250Z' }))

  assert.equal(state.tasksById['task-1'].durationMs, 2250)
  assert.equal(state.tasksById['task-1'].startedAt, '2026-07-30T12:00:00.000Z')
  assert.equal(state.tasksById['task-1'].completedAt, '2026-07-30T12:00:02.250Z')
})

test('failed tasks retain error details and completed tasks survive interruption', () => {
  let state = reduceRunEvent(emptyRunState, event('task.completed', 1, { result: 'healthy' }, { task_id: 'task-ok' }))
  state = reduceRunEvent(state, event('task.failed', 2, { error: { message: 'timeout', code: 'ETIMEDOUT' } }, { task_id: 'task-bad' }))
  state = reduceRunEvent(state, event('stream.interrupted', 3, { error: 'connection lost' }, { task_id: null }))

  assert.equal(state.tasksById['task-ok'].status, 'completed')
  assert.deepEqual(state.tasksById['task-bad'].error, { message: 'timeout', code: 'ETIMEDOUT' })
  assert.equal(state.run.status, 'interrupted')
})
