const BASE = '/api'

export { streamRun } from './runStream'

async function request(endpoint, body = {}) {
  const res = await fetch(`${BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!data.success) throw new Error(data.error || 'Request failed')
  return data.result
}

// ---- Agents ----
export const listAgents = () => request('/agents/list')
export const registerAgent = (agentAddress) => request('/agents/register', { agentAddress })
export const fetchAgentCard = (agentAddress) => request('/agents/fetch-card', { agentAddress })
export const deleteAgent = (agentId) => request('/agents/delete', { agentId })
export const getAgent = (agentId) => request('/agents/get', { agentId })

// ---- Conversations ----
export const createConversation = (agentId, title = 'New Chat', type = 'single') =>
  request('/conversation/create', { agentId, title, type })
export const listConversations = (agentId = '') =>
  request('/conversation/list', { agentId })
export const listConversationsByType = (type = '') =>
  request('/conversation/list', { type })
export const getConversation = (conversationId) =>
  request('/conversation/get', { conversationId })
export const deleteConversation = (conversationId) =>
  request('/conversation/delete', { conversationId })
export const updateConversation = (conversationId, title) =>
  request('/conversation/update', { conversationId, title })

// ---- Messages ----
export const listMessages = (conversationId) =>
  request('/message/list', { conversationId })

export const sendMessage = (conversationId, content) =>
  request('/message/send', { conversation_id: conversationId, content })

// ---- Events ----
export const listEvents = () => request('/events/list')
export const queryEvents = (conversationId) =>
  request('/events/query', { conversationId })

// ---- Health Check ----
export const checkAgentsHealth = () => request('/agents/health-check')

// ---- Orchestration runs & approvals ----
export const listRuns = () => request('/runs/list')
export const getRun = (runId) => request('/runs/get', { run_id: runId })
export const listRunEvents = (runId, afterSequence = 0) => request('/runs/events', { run_id: runId, after_sequence: afterSequence })
export const cancelRun = (runId) => request('/runs/cancel', { run_id: runId })
export const getSystemStatus = () => request('/system/status')
export const listApprovals = (runId = '') =>
  request('/approvals/list', { run_id: runId })
export const decideApproval = (approvalId, decision) =>
  request('/approvals/decide', { approval_id: approvalId, decision })

// ---- Ping ----
export const ping = () => request('/ping')

// ---- Host Agent (blocking compatibility endpoint) ----
export const hostAgents = () => request('/host/agents')
