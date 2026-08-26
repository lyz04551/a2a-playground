import test from 'node:test'
import assert from 'node:assert/strict'
import { canChangeMode, getSystemStatus, getWorkspaceSendState, nextWorkspaceMode, restoreWorkspaceState, selectLatestConversationRun } from './workspace/workspaceState.js'

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

test('restoring a direct conversation uses the deterministically latest run target before legacy agent fallback', () => {
  const latestRun = selectLatestConversationRun('conv-1', [
    { id: 'run-older', conversation_id: 'conv-1', target_agent_id: 'legacy-agent', updated_at: '2026-07-30T10:00:00Z' },
    { id: 'run-other', conversation_id: 'conv-2', target_agent_id: 'other', updated_at: '2026-07-30T12:00:00Z' },
    { id: 'run-newer', conversation_id: 'conv-1', target_agent_id: 'ops-agent', updated_at: '2026-07-30T11:00:00Z' },
  ])
  assert.equal(latestRun.id, 'run-newer')
  assert.equal(restoreWorkspaceState({ id: 'conv-1', type: 'single', agent_id: 'legacy-agent' }, latestRun).selectedAgentId, 'ops-agent')
})
