import test from 'node:test'
import assert from 'node:assert/strict'
import { filterEvents, groupEventsByConversation, summarizeEvent } from './eventFeed.js'

const events = [
  {
    id: 'single-event',
    conversation_id: 'single-1',
    conversation_type: 'single',
    agent_name: 'K8s Ops Agent',
    state: 'completed',
    event_type: 'completed',
    content: '检查完成',
    timestamp: '2026-07-29T10:00:00',
  },
  {
    id: 'multi-event',
    conversation_id: 'multi-1',
    conversation_type: 'multi',
    agent_name: 'K8s Orchestrator Agent',
    state: 'working',
    event_type: 'tool_call',
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
