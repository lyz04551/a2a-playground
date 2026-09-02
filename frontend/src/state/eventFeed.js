export function eventTimestamp(event) {
  return event.timestamp || event.created_at || ''
}

export function groupEventsByConversation(events) {
  const grouped = {}
  for (const event of [...events].sort((a, b) => eventTimestamp(b).localeCompare(eventTimestamp(a)))) {
    const key = event.conversation_id || 'unknown'
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(event)
  }
  return grouped
}

const HOST_EVENT_PREFIXES = ['host.', 'run.', 'message.', 'approval.', 'artifact.']

function agentIdFor(event) {
  return event.agent_id || event.payload?.agent_id || ''
}

function deriveRunMode(run, events) {
  const started = events.find(event => event.event_type === 'run.started')
  return run?.mode || started?.payload?.mode || (events.some(event => event.conversation_type === 'multi') ? 'auto' : 'direct')
}

function deriveStatus(events) {
  const latest = [...events].reverse().find(event => event.state || event.event_type?.startsWith('run.'))
  if (!latest) return 'submitted'
  if (latest.state) return latest.state
  if (latest.event_type === 'run.completed') return 'completed'
  if (latest.event_type === 'run.failed') return 'failed'
  if (latest.event_type === 'run.cancelled') return 'canceled'
  return 'working'
}

function buildTools(events) {
  const tools = new Map()
  for (const event of events.filter(item => item.event_type === 'tool.called' || item.event_type === 'tool.completed')) {
    const payload = event.payload || {}
    const id = payload.tool_call_id || payload.id || event.id
    const existing = tools.get(id) || { id, status: 'working', calledAt: '', completedAt: '' }
    existing.name = payload.tool || payload.tool_name || existing.name || 'Tool call'
    existing.arguments = payload.arguments ?? existing.arguments
    existing.result = payload.result ?? existing.result
    existing.error = payload.error ?? existing.error
    existing.remoteTaskId = payload.remote_task_id || existing.remoteTaskId || ''
    existing.events = [...(existing.events || []), event]
    if (event.event_type === 'tool.called') existing.calledAt = eventTimestamp(event)
    if (event.event_type === 'tool.completed') {
      existing.completedAt = eventTimestamp(event)
      existing.status = event.state === 'failed' || payload.error ? 'failed' : 'completed'
    }
    tools.set(id, existing)
  }
  return [...tools.values()].map(tool => {
    const start = new Date(tool.calledAt).getTime()
    const end = new Date(tool.completedAt).getTime()
    return { ...tool, durationMs: Number.isFinite(start) && Number.isFinite(end) ? end - start : null }
  })
}

function buildTasks(events, agentsById) {
  const grouped = new Map()
  for (const event of events.filter(item => item.task_id)) {
    const task = grouped.get(event.task_id) || { id: event.task_id, events: [] }
    task.events.push(event)
    task.parentTaskId = event.parent_task_id ?? task.parentTaskId ?? null
    task.agentId = agentIdFor(event) || task.agentId || ''
    task.agentName = event.agent_name || task.agentName || ''
    task.remoteTaskId = event.payload?.remote_task_id || task.remoteTaskId || ''
    task.objective = event.payload?.objective || event.payload?.label || task.objective || ''
    grouped.set(event.task_id, task)
  }
  return [...grouped.values()].map(task => ({
    ...task,
    agentName: agentsById.get(task.agentId)?.name || task.agentName || task.agentId || 'Host Agent',
    status: deriveStatus(task.events),
    tools: buildTools(task.events),
    startedAt: eventTimestamp(task.events[0]),
    endedAt: eventTimestamp(task.events.at(-1)),
  }))
}

export function buildEventConversationGroups(events, runs = [], agents = []) {
  const runsById = new Map(runs.map(run => [run.id, run]))
  const agentsById = new Map(agents.map(agent => [agent.id, agent]))
  const conversations = new Map()
  const ordered = [...events].sort((a, b) => eventTimestamp(a).localeCompare(eventTimestamp(b)))

  for (const event of ordered) {
    const conversationId = event.conversation_id || 'unknown'
    const conversation = conversations.get(conversationId) || {
      id: conversationId,
      title: event.conversation_title || '未命名会话',
      type: event.conversation_type || 'single',
      events: [],
      runEvents: new Map(),
    }
    conversation.title = event.conversation_title || conversation.title
    if (event.conversation_type === 'multi') conversation.type = 'multi'
    conversation.events.push(event)
    const runId = event.run_id || `legacy:${conversationId}`
    const runEvents = conversation.runEvents.get(runId) || []
    runEvents.push(event)
    conversation.runEvents.set(runId, runEvents)
    conversations.set(conversationId, conversation)
  }

  return [...conversations.values()].map(conversation => {
    const structuredRuns = [...conversation.runEvents.entries()].map(([id, runEvents]) => {
      const persisted = runsById.get(id)
      const mode = deriveRunMode(persisted, runEvents)
      const started = runEvents.find(event => event.event_type === 'run.started')
      const targetAgentId = persisted?.target_agent_id || started?.payload?.target_agent_id || ''
      return {
        id,
        mode,
        targetAgentId,
        targetAgentName: agentsById.get(targetAgentId)?.name || targetAgentId || '',
        status: deriveStatus(runEvents),
        startedAt: eventTimestamp(runEvents[0]),
        endedAt: eventTimestamp(runEvents.at(-1)),
        events: runEvents,
        tasks: buildTasks(runEvents, agentsById),
        milestones: runEvents.filter(event => HOST_EVENT_PREFIXES.some(prefix => event.event_type?.startsWith(prefix))),
      }
    }).sort((a, b) => b.startedAt.localeCompare(a.startedAt))
    return { ...conversation, runs: structuredRuns, runEvents: undefined }
  }).sort((a, b) => eventTimestamp(b.events.at(-1)).localeCompare(eventTimestamp(a.events.at(-1))))
}

export function filterEvents(events, { type = 'all', state = 'all', query = '' } = {}) {
  const needle = query.trim().toLowerCase()
  return events.filter(event => {
    if (type !== 'all' && event.conversation_type !== type) return false
    if (state !== 'all' && event.state !== state) return false
    if (!needle) return true
    return [
      event.conversation_title,
      event.agent_name,
      event.task_id,
      event.event_type,
      event.content,
      event.payload?.tool,
    ].some(value => String(value || '').toLowerCase().includes(needle))
  })
}

const SUMMARY_TYPES = new Set(['host.plan_created', 'task.delegated', 'task.retry_scheduled', 'task.completed', 'task.failed', 'task.blocked', 'host.synthesis_started', 'message.completed', 'run.completed', 'run.failed', 'run.cancelled'])
const ERROR_TYPES = new Set(['task.retry_scheduled', 'task.failed', 'task.blocked', 'run.failed', 'run.cancelled'])
const TOOL_TYPES = new Set(['tool.called', 'tool.completed'])

export function filterEventsByView(events, view = 'summary') {
  if (view === 'all') return events
  const allowed = view === 'errors' ? ERROR_TYPES : view === 'tools' ? TOOL_TYPES : SUMMARY_TYPES
  return events.filter(event => allowed.has(event.event_type))
}

export function summarizeEvent(event) {
  const tool = event.payload?.tool || event.payload?.tool_name
  if (event.event_type === 'tool.called' && tool) return `调用工具：${tool}`
  if (event.event_type === 'tool.completed' && tool) return `工具完成：${tool}`
  if (event.event_type === 'host.plan_created') return `计划已创建：${event.payload?.summary || event.content || '已生成多智能体任务计划'}`
  if (event.event_type === 'host.planning') return 'Host 正在分析请求并制定计划'
  if (event.event_type === 'host.plan_revised') return `执行计划已调整：${event.payload?.reason || '已更换执行 Agent'}`
  if (event.event_type === 'host.synthesis_started') return 'Host 正在综合各 Agent 的执行结果'
  if (event.event_type === 'task.context_prepared') return `任务上下文已准备${event.payload?.depends_on?.length ? `，依赖 ${event.payload.depends_on.length} 个前序任务` : '，无前置依赖'}`
  if (event.event_type === 'task.delegated') return `任务已分派给 ${event.agent_name || 'Agent'}`
  if (event.event_type === 'task.started') return `${event.agent_name || 'Agent'} 开始执行任务`
  if (event.event_type === 'task.completed') return event.content || `${event.agent_name || 'Agent'} 已完成任务`
  if (event.event_type === 'task.failed') return `任务失败：${event.content || event.payload?.error || '原因未知'}`
  if (event.event_type === 'task.blocked') return `任务阻塞：${event.content || event.payload?.reason || '依赖未满足'}`
  if (event.event_type === 'task.retry_scheduled') return `准备第 ${event.payload?.attempt || '?'} 次尝试：${event.payload?.reason || ''}`
  if (event.event_type === 'task.evaluated') return `结果评价：${event.payload?.outcome || ''}${event.payload?.reason ? `，${event.payload.reason}` : ''}`
  if (event.event_type === 'message.completed') return event.content || 'Host 已生成最终回复'
  if (event.event_type === 'message.delta') return 'Host 正在生成最终回复'
  if (event.event_type === 'approval.required') return '任务等待用户审批'
  if (event.event_type === 'approval.decided') return `审批已处理：${event.payload?.decision || event.payload?.status || ''}`
  if (event.event_type === 'artifact.created') return `已生成产物：${event.payload?.name || event.payload?.id || 'Artifact'}`
  if (event.event_type === 'run.started') return '本次运行已开始'
  if (event.event_type === 'run.completed') return '本次运行已完成'
  if (event.event_type === 'run.failed') return `本次运行失败：${event.content || event.payload?.error || '原因未知'}`
  if (event.event_type === 'run.cancelled') return '本次运行已取消'
  return event.content || '暂无事件详情'
}
