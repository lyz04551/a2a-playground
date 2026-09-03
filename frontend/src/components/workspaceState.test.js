import test from 'node:test'
import assert from 'node:assert/strict'
import { approvalStatusAfterDecision, buildRunReconnectCommand, canChangeMode, enrichWorkspaceMessages, getSystemStatus, getWorkspaceSendState, nextWorkspaceMode, restoreWorkspaceState, selectLatestConversationRun } from './workspace/workspaceState.js'

test('mode can change only before a conversation has messages', () => {
  assert.equal(canChangeMode({ messageCount: 0 }), true)
  assert.equal(canChangeMode({ messageCount: 1 }), false)
})

test('system status maps distinct operational states to accessible labels and icons', () => {
  assert.deepEqual(getSystemStatus({ state: 'offline', kind: 'agent' }), {
    label: 'Agent offline', icon: 'offline', tone: 'muted',
  })
  assert.deepEqual(getSystemStatus({ state: 'missing_model' }), {
    label: 'Model configuration required', icon: 'settings', tone: 'approval',
  })
  assert.deepEqual(getSystemStatus({ state: 'running' }), {
    label: 'Run in progress', icon: 'running', tone: 'orchestration',
  })
  assert.deepEqual(getSystemStatus({ state: 'planning' }), {
    label: 'Run in progress', icon: 'running', tone: 'orchestration',
  })
  assert.deepEqual(getSystemStatus({ state: 'approval_required' }), {
    label: 'Approval required', icon: 'approval', tone: 'approval',
  })
  assert.deepEqual(getSystemStatus({ state: 'failed' }), {
    label: 'Run failed', icon: 'failure', tone: 'danger',
  })
})

test('direct sends require an online selected agent', () => {
  assert.equal(getWorkspaceSendState({ mode: 'direct', agents: [] }).disabled, true)
  assert.equal(getWorkspaceSendState({
    mode: 'direct', selectedAgentId: 'ops', agents: [{ id: 'ops', online: false }],
  }).disabled, true)
  assert.equal(getWorkspaceSendState({
    mode: 'direct', selectedAgentId: 'ops', agents: [{ id: 'ops', online: true }],
  }).disabled, false)
})

test('auto sends require a configured model and an online agent', () => {
  assert.equal(getWorkspaceSendState({ mode: 'auto', modelConfigured: false, agents: [{ id: 'ops', online: true }] }).disabled, true)
  assert.equal(getWorkspaceSendState({ mode: 'auto', modelConfigured: true, agents: [{ id: 'ops', online: false }] }).disabled, true)
  assert.equal(getWorkspaceSendState({ mode: 'auto', modelConfigured: true, agents: [{ id: 'ops', online: true }] }).disabled, false)
})

test('mode changes request a fresh conversation after messages exist', () => {
  assert.deepEqual(nextWorkspaceMode({ mode: 'auto', messageCount: 1 }, 'direct'), { mode: 'direct', needsNewConversation: true })
  assert.deepEqual(nextWorkspaceMode({ mode: 'auto', messageCount: 0 }, 'direct'), { mode: 'direct', needsNewConversation: false })
})

test('restoring a conversation restores its workspace execution context', () => {
  const restored = restoreWorkspaceState({
    id: 'conv-1', mode: 'direct', target_agent_id: 'ops', run: { id: 'run-1' },
    approvals: [{ id: 'approval-1' }], trace: [{ id: 'task-1' }],
  })
  assert.deepEqual(restored, {
    conversationId: 'conv-1', mode: 'direct', selectedAgentId: 'ops', run: { id: 'run-1' },
    approvals: [{ id: 'approval-1' }], tasks: [{ id: 'task-1' }],
  })
})

test('approval follow-up reconnects to an existing run without creating a new one', () => {
  assert.deepEqual(buildRunReconnectCommand({ runId: 'run-1', afterSequence: 42, mode: 'auto', targetAgentId: 'stale' }), {
    run_id: 'run-1', after_sequence: 42, mode: 'auto', message: 'resume',
  })
  assert.deepEqual(buildRunReconnectCommand({ runId: 'run-2', afterSequence: 8, mode: 'direct', targetAgentId: 'ops' }), {
    run_id: 'run-2', after_sequence: 8, mode: 'direct', message: 'resume', target_agent_id: 'ops',
  })
})

test('accepted approval is executing until a terminal run event arrives', () => {
  assert.equal(approvalStatusAfterDecision({ result: { state: 'accepted' } }, 'approved'), 'executing')
  assert.equal(approvalStatusAfterDecision({ result: { state: 'already_decided' } }, 'approved'), 'approved')
  assert.equal(approvalStatusAfterDecision({}, 'rejected'), 'rejected')
})

test('workspace messages display their concrete Agent or Host source', () => {
  const messages = enrichWorkspaceMessages([
    { id: 'user', role: 'user', content: '创建 nginx' },
    { id: 'security', role: 'agent', agentId: 'security', content: '预检通过' },
    { id: 'task-source', role: 'agent', taskId: 'ops-task', content: '检查完成' },
    { id: 'unknown', role: 'agent', agentId: 'removed-agent', content: '旧回复' },
    { id: 'host', role: 'agent', source: 'host', content: '执行完成' },
    { id: 'legacy', role: 'agent', content: '无来源' },
  ], {
    agents: [{ id: 'security', name: 'K8s Security Agent' }, { id: 'ops', name: 'K8s Ops Agent' }],
    tasksById: { 'ops-task': { agentId: 'ops' } },
    language: 'zh-CN',
  })

  assert.deepEqual(messages.map(message => message.agentName), [
    '你', 'K8s Security Agent', 'K8s Ops Agent', 'removed-agent', 'Host Agent 总结', 'Agent',
  ])
})

test('restoring a direct conversation uses the deterministically latest run target before legacy agent fallback', () => {
  const latestRun = selectLatestConversationRun('conv-1', [
    { id: 'run-older', conversation_id: 'conv-1', target_agent_id: 'legacy-agent', updated_at: '2026-07-30T10:00:00Z' },
    { id: 'run-other', conversation_id: 'conv-2', target_agent_id: 'other', updated_at: '2026-07-30T12:00:00Z' },
    { id: 'run-newer', conversation_id: 'conv-1', target_agent_id: 'ops-agent', updated_at: '2026-07-30T11:00:00Z' },
  ])
  assert.equal(latestRun.id, 'run-newer')
  assert.equal(restoreWorkspaceState({ id: 'conv-1', type: 'single', agent_id: 'legacy-agent' }, latestRun).selectedAgentId, 'ops-agent')
})
