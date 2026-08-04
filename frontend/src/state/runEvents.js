const MAX_SEEN_EVENT_IDS = 1000
const MAX_RAW_EVENTS = 500

export const emptyRunState = {
  run: null,
  tasksById: {},
  taskOrder: [],
  messages: [],
  approvals: [],
  artifacts: [],
  seenEventIds: [],
  lastSequence: 0,
  status: 'idle',
  steps: [],
  rawEvents: [],
}

function normalizeTimestamp(value) {
  if (!value) return ''
  const timestamp = new Date(value)
  return Number.isNaN(timestamp.getTime()) ? String(value) : timestamp.toISOString()
}

function legacyEnvelope(event, type, data = {}, taskId = null) {
  return {
    version: 1,
    event_id: `legacy:${type}:${event.id || event.approvalId || event.agent_id || event.type}`,
    sequence: 0,
    run_id: 'legacy',
    conversation_id: 'legacy',
    task_id: taskId,
    parent_task_id: null,
    type,
    timestamp: '',
    data,
  }
}

// This is the sole compatibility boundary for pages still producing the old SSE shapes.
export function normalizeLegacyRunEvent(event) {
  if (event?.version === 1 && event.event_id) return event
  if (!event?.type) return null
  if (event.type === 'run_started') return legacyEnvelope(event, 'run.started')
  if (event.type === 'routing') return legacyEnvelope(event, 'task.delegated', {
    agent_id: event.agent_id || event.agent,
    label: event.agent || event.agent_id,
  }, `agent:${event.agent_id || event.agent}`)
  if (event.type === 'tool_call') return legacyEnvelope(event, 'tool.called', {
    id: event.id,
    tool: event.tool,
    arguments: event.args || {},
  }, event.id || null)
  if (event.type === 'tool_result') return legacyEnvelope(event, 'tool.completed', {
    id: event.id,
    result: event.result,
  }, event.id || null)
  if (event.type === 'approval_required') return legacyEnvelope(event, 'approval.required', event.approval || {})
  if (event.type === 'approval_decided') return legacyEnvelope(event, 'approval.decided', {
    id: event.approvalId,
    decision: event.decision,
  })
  if (event.type === 'artifact') return legacyEnvelope(event, 'artifact.created', event, event.task_id || null)
  if (event.type === 'error') return legacyEnvelope(event, 'run.failed', { error: event.text || event.error })
  if (event.type === 'done') return legacyEnvelope(event, 'run.completed')
  return null
}

function upsertById(items, item) {
  const index = items.findIndex(existing => existing.id === item.id)
  if (index < 0) return [...items, item]
  const next = [...items]
  next[index] = { ...next[index], ...item }
  return next
}

function updateTask(state, event, changes = {}) {
  if (!event.task_id) return state
  const existing = state.tasksById[event.task_id] || {
    id: event.task_id,
    parentTaskId: event.parent_task_id,
    agentId: event.data.agent_id,
    label: event.data.label || event.data.agent_name || event.task_id,
    status: 'queued',
  }
  return {
    ...state,
    tasksById: { ...state.tasksById, [event.task_id]: { ...existing, ...changes } },
    taskOrder: state.tasksById[event.task_id] ? state.taskOrder : [...state.taskOrder, event.task_id],
  }
}

function reduceNormalizedEvent(state, event) {
  const data = event.data || {}
  if (event.type === 'run.started') {
    return { ...state, run: { id: event.run_id, conversationId: event.conversation_id, status: 'running', ...data } }
  }
  if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') {
    return { ...state, run: { ...state.run, id: event.run_id, status: event.type.slice(4), ...data } }
  }
  if (event.type === 'stream.interrupted') {
    return { ...state, run: { ...state.run, id: event.run_id || state.run?.id, status: 'interrupted', ...data } }
  }
  if (event.type === 'host.planning') return { ...state, run: { ...state.run, id: event.run_id, status: 'planning', ...data } }
  if (event.type === 'task.delegated') return updateTask(state, event, {
    status: data.status || 'delegated',
    ...(data.agent_id ? { agentId: data.agent_id } : {}),
    ...(data.label || data.agent_name ? { label: data.label || data.agent_name } : {}),
  })
  if (event.type === 'task.started') return updateTask(state, event, {
    status: 'working',
    startedAt: normalizeTimestamp(event.timestamp),
    ...(data.agent_id ? { agentId: data.agent_id } : {}),
    ...(data.label || data.agent_name ? { label: data.label || data.agent_name } : {}),
  })
  if (event.type === 'task.status_changed') return updateTask(state, event, { status: data.state || data.status || 'working' })
  if (event.type === 'task.completed' || event.type === 'task.failed') {
    const task = state.tasksById[event.task_id]
    const completedAt = normalizeTimestamp(event.timestamp)
    const startedMs = task?.startedAt ? Date.parse(task.startedAt) : NaN
    const completedMs = completedAt ? Date.parse(completedAt) : NaN
    return updateTask(state, event, {
      status: event.type === 'task.completed' ? 'completed' : 'failed',
      completedAt,
      ...(Number.isFinite(startedMs) && Number.isFinite(completedMs) ? { durationMs: Math.max(0, completedMs - startedMs) } : {}),
      ...(event.type === 'task.completed' ? { result: data.result } : { error: data.error }),
    })
  }
  if (event.type === 'tool.called' || event.type === 'tool.completed') {
    const tool = {
      id: data.id || event.event_id,
      ...(data.tool || data.tool_name ? { name: data.tool || data.tool_name } : {}),
      ...(data.arguments || data.args ? { arguments: data.arguments || data.args } : {}),
      status: event.type === 'tool.called' ? 'working' : 'completed',
      ...(data.result === undefined ? {} : { result: data.result }),
    }
    const task = state.tasksById[event.task_id]
    return updateTask(state, event, { tools: upsertById(task?.tools || [], tool) })
  }
  if (event.type === 'message.delta' || event.type === 'message.completed') {
    const id = data.message_id || data.id || `message:${event.task_id || event.event_id}`
    const current = state.messages.find(message => message.id === id)
    const content = event.type === 'message.delta'
      ? `${current?.content || ''}${data.content || data.text || ''}`
      : (data.content || data.text || current?.content || '')
    return { ...state, messages: upsertById(state.messages, { ...current, id, role: data.role || current?.role || 'agent', content, taskId: event.task_id, completed: event.type === 'message.completed' }) }
  }
  if (event.type === 'approval.required') {
    const approval = data.approval || data
    return { ...state, approvals: upsertById(state.approvals, approval), run: { ...state.run, status: 'approval_required' } }
  }
  if (event.type === 'approval.decided') {
    const id = data.id || data.approval_id
    return { ...state, approvals: state.approvals.map(approval => approval.id === id ? { ...approval, status: data.decision || data.status } : approval) }
  }
  if (event.type === 'artifact.created') {
    const artifact = data.artifact || data
    return { ...state, artifacts: upsertById(state.artifacts, artifact) }
  }
  return state
}

// Temporary derived view for the trace components that have not moved to normalized state yet.
export function adaptRunStateForLegacy(state) {
  const steps = state.taskOrder.flatMap(taskId => {
    const task = state.tasksById[taskId]
    const status = task.status === 'delegated' ? 'working' : task.status
    const tools = task.tools || []
    if (tools.length) {
      return tools.map(tool => ({
        id: tool.id,
        kind: 'tool',
        label: tool.name,
        arguments: tool.arguments || {},
        status: tool.status,
        ...(tool.result === undefined ? {} : { result: tool.result }),
      }))
    }
    return [{
      id: task.id,
      kind: 'agent',
      agentId: task.agentId,
      agentName: task.label,
      label: task.label,
      status,
    }]
  })
  return { status: state.run?.status || 'idle', steps }
}

export function reduceRunEvent(state, incomingEvent) {
  const event = normalizeLegacyRunEvent(incomingEvent)
  if (!event || state.seenEventIds.includes(event.event_id)) return state
  const seenEventIds = [...state.seenEventIds, event.event_id].slice(-MAX_SEEN_EVENT_IDS)
  const reduced = reduceNormalizedEvent(state, event)
  const rawEvent = { ...event, timestamp: normalizeTimestamp(event.timestamp) }
  const rawEvents = [...(state.rawEvents || []), rawEvent]
    .sort((left, right) => (left.sequence || 0) - (right.sequence || 0))
    .slice(-MAX_RAW_EVENTS)
  const normalized = { ...reduced, rawEvents, seenEventIds, lastSequence: Math.max(state.lastSequence, event.sequence || 0) }
  return { ...normalized, ...adaptRunStateForLegacy(normalized) }
}
