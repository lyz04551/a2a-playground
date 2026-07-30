const BASE = '/api'

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

export function sendMessageStream(conversationId, content, onEvent, onError, onDone) {
  fetch(`${BASE}/message/send-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, content }),
  })
    .then(async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneCalled = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer && buffer.startsWith('data: ')) {
            try {
              const evt = JSON.parse(buffer.slice(6))
              if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'error') onError?.(evt.text)
              else onEvent?.(evt)
            } catch { }
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === 'error' && onError) onError(evt.text)
              else if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (onEvent) onEvent(evt)
            } catch { /* skip */ }
          }
        }
      }
      if (!doneCalled) onDone?.({})
    })
    .catch(onError || console.error)
}

// ---- Events ----
export const listEvents = () => request('/events/list')
export const queryEvents = (conversationId) =>
  request('/events/query', { conversationId })

// ---- Health Check ----
export const checkAgentsHealth = () => request('/agents/health-check')

// ---- Orchestration runs & approvals ----
export const listRuns = () => request('/runs/list')
export const getRun = (runId) => request('/runs/get', { run_id: runId })
export const listApprovals = (runId = '') =>
  request('/approvals/list', { run_id: runId })
export const decideApproval = (approvalId, decision) =>
  request('/approvals/decide', { approval_id: approvalId, decision })

// ---- Ping ----
export const ping = () => request('/ping')

// ---- Host Agent (simple keyword router) ----
export const hostAgents = () => request('/host/agents')
export const hostSend = (conversationId, content) => request('/host/send', { content, conversation_id: conversationId })

export function hostSendStream(conversationId, content, onEvent, onRouting, onError, onDone) {
  fetch(`${BASE}/host/send-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, conversation_id: conversationId }),
  })
    .then(async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneCalled = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer && buffer.startsWith('data: ')) {
            try {
              const evt = JSON.parse(buffer.slice(6))
              if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'error') onError?.(evt.text)
              else onEvent?.(evt)
            } catch { }
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === 'routing' && onRouting) onRouting(evt)
              else if (evt.type === 'error' && onError) onError(evt.text)
              else if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (onEvent) onEvent(evt)
            } catch { /* skip */ }
          }
        }
      }
      if (!doneCalled) onDone?.({})
    })
    .catch(onError || console.error)
}

// ---- ADK Host Agent (streaming) ----
export function hostAdkSendStream(content, sessionId, onEvent, onToolCall, onToolResult, onRouting, onError, onDone) {
  fetch(`${BASE}/host-adk/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, session_id: sessionId }),
  })
    .then(async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneCalled = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer && buffer.startsWith('data: ')) {
            try {
              const evt = JSON.parse(buffer.slice(6))
              if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'error') onError?.(evt.text)
              else if (evt.type === 'text' && onEvent) onEvent(evt)
            } catch { }
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === 'tool_call' && onToolCall) onToolCall(evt)
              else if (evt.type === 'tool_result' && onToolResult) onToolResult(evt)
              else if (evt.type === 'routing' && onRouting) onRouting(evt)
              else if (evt.type === 'error' && onError) onError(evt.text)
              else if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'text' && onEvent) onEvent(evt)
            } catch { /* skip */ }
          }
        }
      }
      if (!doneCalled) onDone?.({})
    })
    .catch(onError || console.error)
}

// ---- LangGraph Host Agent (Streaming) ----
export function hostLgSendStream(content, sessionId, conversationId, onEvent, onToolCall, onToolResult, onRouting, onApproval, onError, onDone) {
  fetch(`${BASE}/host-lg/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, session_id: sessionId, conversation_id: conversationId || '' }),
  })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text()
        if (onError) onError(`HTTP ${res.status}: ${text}`)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneCalled = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer && buffer.startsWith('data: ')) {
            try {
              const evt = JSON.parse(buffer.slice(6))
              if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'error') onError?.(evt.text)
              else if (evt.type === 'text' && onEvent) onEvent(evt)
            } catch { }
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === 'tool_call' && onToolCall) onToolCall(evt)
              else if (evt.type === 'tool_result' && onToolResult) onToolResult(evt)
              else if (evt.type === 'routing' && onRouting) onRouting(evt)
              else if (evt.type === 'approval_required' && onApproval) onApproval(evt)
              else if (evt.type === 'error' && onError) onError(evt.text)
              else if (evt.type === 'done') { doneCalled = true; onDone?.(evt) }
              else if (evt.type === 'text' && onEvent) onEvent(evt)
            } catch { /* skip */ }
          }
        }
      }
      if (!doneCalled) onDone?.({})
    })
    .catch(onError || console.error)
}
