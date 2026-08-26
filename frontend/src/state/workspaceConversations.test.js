import test from 'node:test'
import assert from 'node:assert/strict'
import { filterConversations, normalizeConversationTitle } from './workspaceConversations.js'

const conversations = [
  { id: '1', title: '集群健康检查', agent_name: 'K8s Ops' },
  { id: '2', title: 'RBAC review', agent_name: 'Security Agent' },
]

test('filters conversations by title and Agent name', () => {
  assert.deepEqual(filterConversations(conversations, '健康').map(item => item.id), ['1'])
  assert.deepEqual(filterConversations(conversations, 'security').map(item => item.id), ['2'])
})

test('returns the original conversation order for an empty query', () => {
  assert.deepEqual(filterConversations(conversations, '').map(item => item.id), ['1', '2'])
})

test('trims and limits conversation titles', () => {
  assert.equal(normalizeConversationTitle('  new title  '), 'new title')
  assert.equal(normalizeConversationTitle('x'.repeat(100)).length, 80)
  assert.equal(normalizeConversationTitle('   '), '')
})
