import test from 'node:test'
import assert from 'node:assert/strict'
import { filterEvents, filterEventsByView, groupEventsByConversation, summarizeEvent } from './eventFeed.js'

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
