import test from 'node:test'
import assert from 'node:assert/strict'
import { searchCommands } from './commandSearch.js'

const commands = [
  { id: 'events', title: '执行事件', subtitle: 'Agent activity', type: 'page', keywords: ['event'] },
  { id: 'agent-ops', title: 'K8s Ops Agent', subtitle: '运维', type: 'agent', keywords: ['kubernetes'] },
  { id: 'conversation', title: '集群检查', subtitle: 'K8s Ops Agent', type: 'conversation', keywords: ['health'] },
]

test('ranks title matches before metadata matches', () => {
  const results = searchCommands(commands, 'agent')
  assert.equal(results[0].id, 'agent-ops')
  assert.equal(results[1].id, 'events')
})

test('matches case-insensitively across keywords', () => {
  assert.equal(searchCommands(commands, 'KUBERNETES')[0].id, 'agent-ops')
})

test('filters by command type', () => {
  assert.deepEqual(searchCommands(commands, '', { type: 'conversation' }).map(item => item.id), ['conversation'])
})

test('keeps stable defaults and limits the result count', () => {
  const many = Array.from({ length: 30 }, (_, index) => ({ id: String(index), title: `Item ${index}`, type: 'page' }))
  assert.deepEqual(searchCommands(many, '', { limit: 3 }).map(item => item.id), ['0', '1', '2'])
})
