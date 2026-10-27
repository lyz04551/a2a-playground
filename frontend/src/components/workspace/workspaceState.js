const statusByState = {
  offline: { label: 'Agent offline', icon: 'offline', tone: 'muted' },
  missing_model: { label: 'Model configuration required', icon: 'settings', tone: 'approval' },
  running: { label: 'Run in progress', icon: 'running', tone: 'orchestration' },
  planning: { label: 'Run in progress', icon: 'running', tone: 'orchestration' },
  approval_required: { label: 'Approval required', icon: 'approval', tone: 'approval' },
  failed: { label: 'Run failed', icon: 'failure', tone: 'danger' },
  partial: { label: '部分完成', icon: 'approval', tone: 'approval' },
  evidence_insufficient: { label: '证据不足而终止', icon: 'failure', tone: 'danger' },
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

export function resolveWorkspaceRefreshResults(results, previous = {}) {
  const [listed, health, status, saved] = results
  const agents = listed?.status === 'fulfilled' ? listed.value : (previous.agents || [])
  const healthMap = health?.status === 'fulfilled' ? health.value : null
  return {
    agents: agents.map(agent => ({
      ...agent,
      online: healthMap ? Boolean(healthMap[agent.id]?.online) : Boolean(agent.online ?? agent.health?.online),
    })),
    modelConfigured: status?.status === 'fulfilled' ? Boolean(status.value.model?.configured) : Boolean(previous.modelConfigured),
    conversations: saved?.status === 'fulfilled' ? saved.value : (previous.conversations || []),
  }
}

export function getWorkspaceGaps(tasks = []) {
  return tasks.filter(task => task.evaluation === 'insufficient').map(task => ({
    taskId: task.id,
    objective: task.objective || task.label || task.id,
    reason: task.evaluationReason || '',
    missingTargets: [...new Set((task.coverage?.expected_targets || []).filter(target => !(task.coverage?.inspected_targets || []).includes(target)))],
  }))
}

export function getCoveragePresentation(tasks = []) {
  const audited = tasks.filter(task => task.coverageRequired === true && task.coverage)
  if (!audited.length) return null
  const expected = new Set(audited.flatMap(task => task.coverage.expected_targets || []))
  const inspected = new Set(audited.flatMap(task => task.coverage.inspected_targets || []))
  const missing = [...expected].filter(target => !inspected.has(target))
  const enumerationComplete = audited.every(task => task.coverage.enumeration_complete === true)
  return {
    checked: [...expected].filter(target => inspected.has(target)).length,
    total: expected.size,
    missing,
    enumerationComplete,
    complete: enumerationComplete && missing.length === 0 && audited.every(task => task.evaluation !== 'insufficient'),
  }
}

export function buildContinuationPrompt(gaps = [], language = 'zh-CN') {
  const lines = gaps.flatMap(gap => gap.missingTargets.length ? gap.missingTargets.map(target => `- ${target}`) : [`- ${gap.objective}: ${gap.reason}`])
  return language === 'zh-CN'
    ? `请继续本会话尚未完成的只读检查，只补充以下缺口，不要重复已完成的枚举和检查。沿用上次工具证据；如果证据已失效，请说明后再重新获取。未能验证的项明确标为未知：\n${lines.join('\n')}`
    : `Continue the incomplete read-only checks in this conversation. Inspect only these gaps; do not repeat completed discovery or inspections. Reuse prior tool evidence, and explain any required refresh. Mark unverified items as unknown:\n${lines.join('\n')}`
}

export function nextWorkspaceMode({ messageCount = 0 } = {}, mode) {
  return { mode, needsNewConversation: !canChangeMode({ messageCount }) }
}

export function buildRunReconnectCommand({ runId, afterSequence = 0, mode = 'auto', targetAgentId = '' }) {
  return {
    run_id: runId,
    after_sequence: afterSequence,
    mode,
    message: 'resume',
    ...(mode === 'direct' ? { target_agent_id: targetAgentId } : {}),
  }
}

export function approvalStatusAfterDecision(response = {}, decision) {
  return response.result?.state === 'accepted' ? 'executing' : decision
}

const comparableContent = value => typeof value === 'string' ? value.trim() : JSON.stringify(value ?? '')

export function enrichWorkspaceMessages(messages = [], { agents = [], tasksById = {}, hostSummary = '', language = 'zh-CN' } = {}) {
  const namesById = new Map(agents.map(agent => [agent.id, agent.name || agent.id]))
  const tasks = Object.values(tasksById)
  const zh = language === 'zh-CN'
  return messages.map(message => {
    if (message.role === 'user') return { ...message, agentName: zh ? '你' : 'You' }
    const content = comparableContent(message.content)
    const inferredTask = tasks.find(task => [task.output, task.streamingOutput, task.result].some(output => output != null && comparableContent(output) === content))
    const isHost = message.source === 'host' || message.metadata?.source === 'host' || (hostSummary && comparableContent(hostSummary) === content)
    if (isHost) return { ...message, source: 'host', agentName: zh ? 'Host Agent 总结' : 'Host Agent summary' }
    const agentId = message.agentId || message.agent_id || message.metadata?.agent_id || tasksById[message.taskId]?.agentId || inferredTask?.agentId || ''
    return { ...message, agentId, agentName: message.agentName || namesById.get(agentId) || agentId || 'Agent' }
  })
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
