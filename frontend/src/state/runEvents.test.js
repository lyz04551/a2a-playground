import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyRunState, normalizeLegacyRunEvent, reduceRunEvent, restoreRunEventState } from './runEvents.js'

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

  assert.deepEqual(state.messages, [{ id: 'msg-1', role: 'agent', content: 'Hello', taskId: 'task-1', agentId: '', source: 'host', completed: true }])
  assert.equal(state.approvals[0].id, 'approval-1')
  assert.equal(state.approvals[0].taskId, 'task-1')
  assert.equal(state.artifacts[0].name, 'plan.yaml')
  assert.equal(state.run.status, 'completed')
})

test('duplicate envelopes leave normalized state unchanged', () => {
  const started = event('run.started', 1)
  const once = reduceRunEvent(emptyRunState, started)
  const twice = reduceRunEvent(once, started)

  assert.strictEqual(twice, once)
})

test('terminal run failure closes an unfinished host round and active task', () => {
  let state = reduceRunEvent(emptyRunState, event('run.started', 1))
  state = reduceRunEvent(state, event('host.round_started', 2, { round: 5 }))
  state = reduceRunEvent(state, event('task.started', 3, { agent_id: 'ops' }, { task_id: 'task-active' }))
  state = reduceRunEvent(state, event('run.failed', 4, { error: 'Unable to create a valid Host decision' }, { task_id: null }))

  assert.equal(state.roundsByNumber[5].status, 'failed')
  assert.equal(state.tasksById['task-active'].status, 'failed')
  assert.equal(state.run.status, 'failed')
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

test('merges tool completion by tool_call_id and derives its duration', () => {
  let state = reduceRunEvent(emptyRunState, event('task.delegated', 1, { agent_id: 'ops' }))
  state = reduceRunEvent(state, event('tool.called', 2, {
    tool_call_id: 'call-1', tool: 'get_nodes', arguments: { wide: true },
  }, { timestamp: '2026-07-30T12:00:00Z' }))
  state = reduceRunEvent(state, event('tool.completed', 3, {
    tool_call_id: 'call-1', tool: 'get_nodes', result: 'Ready',
  }, { timestamp: '2026-07-30T12:00:01.250Z' }))

  assert.equal(state.tasksById['task-1'].tools.length, 1)
  assert.deepEqual(state.tasksById['task-1'].tools[0], {
    id: 'call-1', name: 'get_nodes', arguments: { wide: true }, status: 'completed',
    result: 'Ready', startedAt: '2026-07-30T12:00:00.000Z',
    completedAt: '2026-07-30T12:00:01.250Z', durationMs: 1250,
  })
})

test('terminal task event closes an orphaned working tool from an approval resume', () => {
  let state = reduceRunEvent(emptyRunState, event('tool.called', 1, {
    tool_call_id: 'call-write', tool: 'apply_k8s_yaml', arguments: { yaml: 'kind: Pod' },
  }, { timestamp: '2026-09-03T10:00:00Z' }))

  state = reduceRunEvent(state, event('task.completed', 2, {
    result: 'Pod/nginx-secure-002 created',
  }, { timestamp: '2026-09-03T10:00:28Z' }))

  assert.deepEqual(state.tasksById['task-1'].tools[0], {
    id: 'call-write', name: 'apply_k8s_yaml', arguments: { yaml: 'kind: Pod' },
    status: 'completed', result: 'Pod/nginx-secure-002 created',
    startedAt: '2026-09-03T10:00:00.000Z',
    completedAt: '2026-09-03T10:00:28.000Z', durationMs: 28000,
  })
})

test('failed tasks retain error details and completed tasks survive interruption', () => {
  let state = reduceRunEvent(emptyRunState, event('task.completed', 1, { result: 'healthy' }, { task_id: 'task-ok' }))
  state = reduceRunEvent(state, event('task.failed', 2, { error: { message: 'timeout', code: 'ETIMEDOUT' } }, { task_id: 'task-bad' }))
  state = reduceRunEvent(state, event('stream.interrupted', 3, { error: 'connection lost' }, { task_id: null }))

  assert.equal(state.tasksById['task-ok'].status, 'completed')
  assert.deepEqual(state.tasksById['task-bad'].error, { message: 'timeout', code: 'ETIMEDOUT' })
  assert.equal(state.run.status, 'interrupted')
})

test('multi-agent plan retains dependencies retries replacement and blocked state', () => {
  let state = reduceRunEvent(emptyRunState, event('host.plan_created', 1, {
    summary: 'diagnose and review',
    tasks: [
      { id: 'diagnose', agent_id: 'ops', depends_on: [] },
      { id: 'security', agent_id: 'security', depends_on: [] },
      { id: 'remediate', agent_id: 'orchestrator', objective: '生成修复结论', input: '综合前序结果', completion_criteria: ['给出优先级'], depends_on: ['diagnose', 'security'] },
    ],
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('task.delegated', 2, { agent_id: 'ops' }, { task_id: 'diagnose', parent_task_id: 'root' }))
  state = reduceRunEvent(state, event('task.retry_scheduled', 3, { agent_id: 'ops', attempt: 2, reason: 'timeout' }, { task_id: 'diagnose', parent_task_id: 'root' }))
  state = reduceRunEvent(state, event('host.plan_revised', 4, { agent_id: 'fallback', replacement_agent_id: 'fallback' }, { task_id: 'diagnose', parent_task_id: 'root' }))
  state = reduceRunEvent(state, event('task.blocked', 5, { reason: 'dependency unavailable' }, { task_id: 'remediate', parent_task_id: 'root' }))

  assert.deepEqual(state.plan.taskIds, ['diagnose', 'security', 'remediate'])
  assert.deepEqual(state.tasksById.remediate.dependsOn, ['diagnose', 'security'])
  assert.equal(state.tasksById.remediate.objective, '生成修复结论')
  assert.equal(state.tasksById.remediate.input, '综合前序结果')
  assert.deepEqual(state.tasksById.remediate.completionCriteria, ['给出优先级'])
  assert.equal(state.tasksById.diagnose.attempt, 2)
  assert.equal(state.tasksById.diagnose.replacedAgentId, 'fallback')
  assert.equal(state.tasksById.remediate.status, 'blocked')
})

test('restores task details and results by replaying persisted events', () => {
  const rawEvents = [
    event('run.started', 1),
    event('host.plan_created', 2, { tasks: [{ id: 'ops', agent_id: 'ops-agent', objective: '检查集群', input: '当前状态', depends_on: [] }] }),
    event('task.completed', 3, { result: '集群健康' }, { task_id: 'ops', parent_task_id: 'root' }),
  ]
  const state = restoreRunEventState({ run: { id: 'run-1', status: 'completed' }, rawEvents })
  assert.equal(state.tasksById.ops.objective, '检查集群')
  assert.equal(state.tasksById.ops.result, '集群健康')
})

test('keeps each agent output and host summary in separate replayable state', () => {
  let state = reduceRunEvent(emptyRunState, event('host.plan_created', 1, {
    tasks: [
      { id: 'security', agent_id: 'security', objective: '安全检查' },
      { id: 'change', agent_id: 'orchestrator', objective: '创建资源' },
    ],
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('message.delta', 2, {
    content: '安全', agent_id: 'security',
  }, { task_id: 'security', parent_task_id: 'root' }))
  state = reduceRunEvent(state, event('message.completed', 3, {
    content: '安全检查通过', agent_id: 'security',
  }, { task_id: 'security', parent_task_id: 'root' }))
  state = reduceRunEvent(state, event('message.completed', 4, {
    content: '部署和验证均已完成',
  }, { task_id: 'root', parent_task_id: null }))

  assert.equal(state.tasksById.security.output, '安全检查通过')
  assert.equal(state.tasksById.change.output, undefined)
  assert.equal(state.hostSummary, '部署和验证均已完成')
  assert.deepEqual(state.messages.map(message => ({ content: message.content, agentId: message.agentId, source: message.source })), [
    { content: '安全检查通过', agentId: 'security', source: 'agent' },
    { content: '部署和验证均已完成', agentId: '', source: 'host' },
  ])

  const restored = restoreRunEventState({ rawEvents: state.rawEvents })
  assert.equal(restored.tasksById.security.output, '安全检查通过')
  assert.equal(restored.hostSummary, '部署和验证均已完成')
  assert.equal(restored.messages[0].agentId, 'security')
  assert.equal(restored.messages[1].source, 'host')
})

test('appends react decision rounds and only their newly introduced tasks', () => {
  let state = reduceRunEvent(emptyRunState, event('host.round_started', 1, {
    round: 1,
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('host.decision_created', 2, {
    round: 1,
    action: 'delegate',
    reason: '并行执行安全和容量检查',
    tasks: [
      { id: 'security', agent_id: 'security', objective: '安全检查' },
      { id: 'capacity', agent_id: 'capacity', objective: '容量检查' },
    ],
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('host.round_completed', 3, {
    round: 1,
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('host.round_started', 4, {
    round: 2,
  }, { task_id: 'root' }))
  state = reduceRunEvent(state, event('host.decision_created', 5, {
    round: 2,
    action: 'delegate',
    reason: '检查通过后创建资源',
    tasks: [
      { id: 'orchestrator', agent_id: 'orchestrator', objective: '创建 nginx' },
    ],
  }, { task_id: 'root' }))

  assert.deepEqual(state.roundOrder, [1, 2])
  assert.deepEqual(state.roundsByNumber[1].taskIds, ['security', 'capacity'])
  assert.equal(state.roundsByNumber[1].status, 'completed')
  assert.deepEqual(state.roundsByNumber[2].taskIds, ['orchestrator'])
  assert.deepEqual(state.taskOrder, ['security', 'capacity', 'orchestrator'])
  assert.equal(state.tasksById.security.round, 1)
  assert.equal(state.tasksById.orchestrator.round, 2)

  const restored = restoreRunEventState({ rawEvents: state.rawEvents })
  assert.deepEqual(restored.roundOrder, [1, 2])
  assert.deepEqual(restored.taskOrder, state.taskOrder)
})
