import test from 'node:test'
import assert from 'node:assert/strict'
import { buildEventConversationGroups, filterEvents, filterEventsByView, groupEventsByConversation, summarizeEvent } from './eventFeed.js'

const events = [
  {
    id: 'single-event',
    conversation_id: 'single-1',
    conversation_type: 'single',
    agent_name: 'K8s Ops Agent',
    state: 'completed',
    event_type: 'task.completed',
    content: '检查完成',
    timestamp: '2026-07-29T10:00:00',
  },
  {
    id: 'multi-event',
    conversation_id: 'multi-1',
    conversation_type: 'multi',
    agent_name: 'K8s Orchestrator Agent',
    state: 'working',
    event_type: 'tool.called',
    payload: { tool: 'scale_k8s_deployment' },
    timestamp: '2026-07-29T10:01:00',
  },
]

test('event feed keeps both single and multi-agent conversations', () => {
  const grouped = groupEventsByConversation(events)
  assert.deepEqual(Object.keys(grouped), ['multi-1', 'single-1'])
})

test('event feed filters by conversation type and search text', () => {
  assert.deepEqual(
    filterEvents(events, { type: 'multi', query: 'orchestrator' }).map(e => e.id),
    ['multi-event'],
  )
})

test('tool events use the tool name as their readable summary', () => {
  assert.equal(summarizeEvent(events[1]), '调用工具：scale_k8s_deployment')
})

test('versioned run events produce readable Chinese summaries', () => {
  assert.equal(summarizeEvent({ event_type: 'host.plan_created', payload: { summary: '并行检查两个方面' } }), '计划已创建：并行检查两个方面')
  assert.equal(summarizeEvent({ event_type: 'task.started', agent_name: 'K8s Ops Agent' }), 'K8s Ops Agent 开始执行任务')
  assert.equal(summarizeEvent({ event_type: 'run.completed' }), '本次运行已完成')
})

test('event views keep summary, errors, tools, or all events', () => {
  const source = [
    { event_type: 'host.plan_created' }, { event_type: 'task.started' },
    { event_type: 'task.retry_scheduled' }, { event_type: 'task.failed' },
    { event_type: 'tool.called' }, { event_type: 'tool.completed' },
    { event_type: 'message.delta' }, { event_type: 'run.completed' },
  ]
  assert.deepEqual(filterEventsByView(source, 'summary').map(e => e.event_type), ['host.plan_created', 'task.retry_scheduled', 'task.failed', 'run.completed'])
  assert.deepEqual(filterEventsByView(source, 'errors').map(e => e.event_type), ['task.retry_scheduled', 'task.failed'])
  assert.deepEqual(filterEventsByView(source, 'tools').map(e => e.event_type), ['tool.called', 'tool.completed'])
  assert.equal(filterEventsByView(source, 'all').length, source.length)
})

test('structured event feed separates runs and identifies direct and auto modes', () => {
  const source = [
    { id: 'direct-start', conversation_id: 'conversation-1', conversation_title: '集群检查', conversation_type: 'single', run_id: 'run-direct', event_type: 'run.started', payload: { mode: 'direct', target_agent_id: 'ops' }, timestamp: '2026-09-02T10:00:00Z' },
    { id: 'auto-start', conversation_id: 'conversation-1', conversation_title: '集群检查', conversation_type: 'multi', run_id: 'run-auto', event_type: 'run.started', payload: { mode: 'auto' }, timestamp: '2026-09-02T11:00:00Z' },
  ]
  const groups = buildEventConversationGroups(source, [
    { id: 'run-direct', mode: 'direct', target_agent_id: 'ops' },
    { id: 'run-auto', mode: 'auto' },
  ], [{ id: 'ops', name: 'K8s Ops Agent' }])

  assert.equal(groups.length, 1)
  assert.deepEqual(groups[0].runs.map(run => run.id), ['run-auto', 'run-direct'])
  assert.equal(groups[0].runs[0].mode, 'auto')
  assert.equal(groups[0].runs[1].mode, 'direct')
  assert.equal(groups[0].runs[1].targetAgentName, 'K8s Ops Agent')
})

test('structured event feed merges tool lifecycle by call id without losing details', () => {
  const source = [
    { id: 'called', conversation_id: 'conversation-1', run_id: 'run-1', task_id: 'task-1', agent_id: 'ops', event_type: 'tool.called', payload: { tool_call_id: 'call-1', tool: 'list_k8s_nodes', arguments: { wide: true }, remote_task_id: 'remote-1' }, timestamp: '2026-09-02T10:00:01Z' },
    { id: 'completed', conversation_id: 'conversation-1', run_id: 'run-1', task_id: 'task-1', agent_id: 'ops', event_type: 'tool.completed', state: 'completed', payload: { tool_call_id: 'call-1', tool: '', result: [{ name: 'node-1' }], remote_task_id: 'remote-1' }, timestamp: '2026-09-02T10:00:03Z' },
  ]
  const [conversation] = buildEventConversationGroups(source, [{ id: 'run-1', mode: 'direct' }], [{ id: 'ops', name: 'K8s Ops Agent' }])
  const [task] = conversation.runs[0].tasks
  const [tool] = task.tools

  assert.equal(task.remoteTaskId, 'remote-1')
  assert.equal(task.agentName, 'K8s Ops Agent')
  assert.equal(tool.id, 'call-1')
  assert.equal(tool.name, 'list_k8s_nodes')
  assert.deepEqual(tool.arguments, { wide: true })
  assert.deepEqual(tool.result, [{ name: 'node-1' }])
  assert.equal(tool.status, 'completed')
  assert.equal(tool.durationMs, 2000)
})

test('structured event feed preserves A2A task hierarchy and host milestones', () => {
  const source = [
    { id: 'planning', conversation_id: 'conversation-1', run_id: 'run-1', event_type: 'host.plan_created', payload: { summary: '检查集群' }, timestamp: '2026-09-02T10:00:00Z' },
    { id: 'root', conversation_id: 'conversation-1', run_id: 'run-1', task_id: 'root-task', parent_task_id: null, event_type: 'task.started', agent_name: 'Host Agent', timestamp: '2026-09-02T10:00:01Z' },
    { id: 'child', conversation_id: 'conversation-1', run_id: 'run-1', task_id: 'ops-task', parent_task_id: 'root-task', agent_id: 'ops', event_type: 'task.delegated', payload: { remote_task_id: 'remote-ops' }, timestamp: '2026-09-02T10:00:02Z' },
  ]
  const [conversation] = buildEventConversationGroups(source, [{ id: 'run-1', mode: 'auto' }], [{ id: 'ops', name: 'K8s Ops Agent' }])
  const run = conversation.runs[0]

  assert.deepEqual(run.milestones.map(event => event.id), ['planning'])
  assert.equal(run.tasks.find(task => task.id === 'ops-task').parentTaskId, 'root-task')
})
