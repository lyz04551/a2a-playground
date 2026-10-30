import test from 'node:test'
import assert from 'node:assert/strict'
import { groupAgentDrafts, visibleConversationMessages } from './messageGrouping.js'

test('keeps earlier tool-superseded drafts inside the current Agent card', () => {
  const messages = [
    { id: 'user', role: 'user', content: '检查安全风险' },
    { id: 'progress:security', role: 'agent', taskId: 'security', progress: true, content: '先检查 RBAC' },
    { id: 'message:security', role: 'agent', taskId: 'security', content: '正在检查 Pod', completed: false },
  ]
  const grouped = groupAgentDrafts(messages)
  assert.equal(grouped.length, 2)
  assert.equal(grouped[1].content, '正在检查 Pod')
  assert.equal(grouped[1].draftContent, '先检查 RBAC')
})

test('keeps a draft visible when no current report exists', () => {
  const grouped = groupAgentDrafts([{ id: 'progress:security', role: 'agent', taskId: 'security', progress: true, content: '检查中' }])
  assert.equal(grouped.length, 1)
  assert.equal(grouped[0].content, '检查中')
})

test('generated progress records stay out of the conversation while agent reports remain', () => {
  const messages = [
    { id: 'user', role: 'user', content: '检查安全风险' },
    { id: 'progress:security', role: 'agent', taskId: 'security', progress: true, content: '先检查 RBAC' },
    { id: 'message:security', role: 'agent', taskId: 'security', content: '现在枚举 Service、NetworkP', completed: false },
    { id: 'message:ops', role: 'agent', taskId: 'ops', content: 'Ops 已完成', completed: true },
  ]
  assert.deepEqual(visibleConversationMessages(messages, true).map(message => message.id), ['user', 'message:security', 'message:ops'])
  assert.deepEqual(visibleConversationMessages(messages, false).map(message => message.id), ['user', 'message:security', 'message:ops'])
})
