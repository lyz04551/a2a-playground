const statusByState = {
  offline: { label: 'Agent offline', icon: 'offline', tone: 'muted' },
  missing_model: { label: 'Model configuration required', icon: 'settings', tone: 'approval' },
  running: { label: 'Run in progress', icon: 'running', tone: 'orchestration' },
  approval_required: { label: 'Approval required', icon: 'approval', tone: 'approval' },
  failed: { label: 'Run failed', icon: 'failure', tone: 'danger' },
  completed: { label: 'Run completed', icon: 'success', tone: 'primary' },
  online: { label: 'System online', icon: 'success', tone: 'primary' },
}

export function canChangeMode({ messageCount = 0 } = {}) {
  return Number(messageCount) === 0
}

export function getSystemStatus({ state = 'online' } = {}) {
  return statusByState[state] || { label: 'Status unknown', icon: 'unknown', tone: 'muted' }
}

export function getWorkspaceSendState({ mode = 'auto', selectedAgentId = '', agents = [], modelConfigured = false } = {}) {
  const onlineAgents = agents.filter(agent => agent.online !== false)
  if (mode === 'direct') {
    const selectedAgent = onlineAgents.find(agent => agent.id === selectedAgentId)
    return selectedAgent ? { disabled: false, reason: '' } : { disabled: true, reason: 'Select an online Agent to send directly.' }
  }
  if (!modelConfigured) return { disabled: true, reason: 'Configure a model to use Auto mode.' }
  if (!onlineAgents.length) return { disabled: true, reason: 'No online Agents are available for Auto mode.' }
  return { disabled: false, reason: '' }
}

export function nextWorkspaceMode({ messageCount = 0 } = {}, mode) {
  return { mode, needsNewConversation: !canChangeMode({ messageCount }) }
}

function runSortValue(run = {}) {
  return Date.parse(run.updated_at || run.updatedAt || run.created_at || run.createdAt || '') || 0
}

export function selectLatestConversationRun(conversationId, runs = []) {
  return runs
    .filter(run => (run.conversation_id || run.conversationId) === conversationId)
    .sort((left, right) => runSortValue(right) - runSortValue(left) || String(right.id || '').localeCompare(String(left.id || '')))[0] || null
}

export function restoreWorkspaceState(conversation = {}, latestRun = null) {
  return {
    conversationId: conversation.id || conversation.conversation_id || null,
    mode: conversation.mode || (conversation.type === 'single' ? 'direct' : 'auto'),
    selectedAgentId: conversation.target_agent_id || conversation.targetAgentId || latestRun?.target_agent_id || latestRun?.targetAgentId || conversation.agent_id || '',
    run: conversation.run || latestRun || null,
    approvals: conversation.approvals || [],
    tasks: conversation.trace || conversation.tasks || [],
  }
}
