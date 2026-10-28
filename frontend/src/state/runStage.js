const TERMINAL_TASKS = new Set(['task.completed', 'task.failed', 'task.blocked'])

function timingPhase(event) {
  if (event.type === 'tool.called') return 'tool'
  if (event.type === 'tool.completed' || event.type === 'agent.thinking_delta') return 'analysis'
  if (event.type === 'message.delta') return event.data?.agent_id ? 'agent-writing' : 'host-writing'
  if (event.type === 'host.planning') return 'planning'
  if (event.type === 'host.synthesis_started') return 'synthesis'
  return event.type
}

export function deriveRunStageTiming(events = [], now = Date.now()) {
  const latest = events.at(-1)
  const latestAt = Date.parse(latest?.timestamp || '')
  if (!Number.isFinite(latestAt)) return { stageSeconds: 0, silentSeconds: 0 }
  const phase = timingPhase(latest)
  let firstAt = latestAt
  for (let index = events.length - 2; index >= 0; index -= 1) {
    if (timingPhase(events[index]) !== phase) break
    const at = Date.parse(events[index].timestamp || '')
    if (Number.isFinite(at)) firstAt = at
  }
  return {
    stageSeconds: Math.max(0, Math.floor((now - firstAt) / 1000)),
    silentSeconds: Math.max(0, Math.floor((now - latestAt) / 1000)),
  }
}

export function deriveRunStage(events = [], agents = []) {
  const ordered = [...events].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
  const latest = ordered.at(-1)
  const tasks = new Map()
  const plan = ordered.findLast?.(item => item.type === 'host.plan_created')
  for (const item of plan?.data?.tasks || []) tasks.set(item.id, { id: item.id, objective: item.objective, agentId: item.agent_id, active: false })
  for (const item of ordered) {
    if (!item.task_id) continue
    const task = tasks.get(item.task_id) || { id: item.task_id }
    if (item.data?.agent_id) task.agentId = item.data.agent_id
    if (item.type === 'task.delegated' || item.type === 'task.started' || item.type === 'task.retry_scheduled') task.active = true
    if (TERMINAL_TASKS.has(item.type)) task.active = false
    tasks.set(item.task_id, task)
  }
  const active = [...tasks.values()].filter(task => task.active).map(task => ({
    ...task,
    agentName: agents.find(agent => agent.id === task.agentId)?.name || task.agentId || 'Agent',
  }))
  if (!latest) return { state: 'idle', textZh: '', textEn: '', active }
  if (latest.type === 'run.completed') return { state: 'completed', textZh: '运行已完成', textEn: 'Run completed', active: [] }
  if (latest.type === 'run.partial') return { state: 'partial', textZh: '部分完成：仍有检查缺少充分证据', textEn: 'Partially completed: some checks lack sufficient evidence', active: [] }
  if (latest.type === 'run.evidence_insufficient') return { state: 'evidence_insufficient', textZh: '证据不足而终止', textEn: 'Stopped: insufficient evidence', active: [] }
  if (latest.type === 'run.failed') return { state: 'failed', textZh: `运行失败：${latest.data?.error || '原因未知'}`, textEn: `Run failed: ${latest.data?.error || 'unknown error'}`, active: [] }
  if (latest.type === 'run.cancelled') return { state: 'cancelled', textZh: '运行已取消', textEn: 'Run cancelled', active: [] }
  if (latest.type === 'host.planning') return { state: 'planning', textZh: 'Host 正在分析请求并制定计划…', textEn: 'Host is analyzing the request and creating a plan…', active }
  if (latest.type === 'host.plan_created') {
    const count = latest.data?.tasks?.length || 0
    return { state: 'planned', textZh: `已创建 ${count} 个任务…`, textEn: `Created ${count} tasks…`, active }
  }
  if (latest.type === 'host.synthesis_started') return { state: 'synthesizing', textZh: 'Host 正在综合各 Agent 结果…', textEn: 'Host is synthesizing Agent results…', active }
  if (latest.type === 'message.delta' && latest.data?.agent_id) {
    const agentId = latest.data.agent_id
    const agentName = agents.find(agent => agent.id === agentId)?.name || agentId
    return { state: 'working', textZh: `${agentName} 正在生成回复…`, textEn: `${agentName} is generating a response…`, active }
  }
  if (latest.type === 'message.delta') return { state: 'responding', textZh: 'Host 正在生成最终回复…', textEn: 'Host is generating the final response…', active }
  if (latest.type === 'agent.thinking_delta') {
    const agentId = latest.data?.agent_id || tasks.get(latest.task_id)?.agentId
    const agentName = agents.find(agent => agent.id === agentId)?.name || agentId || 'Agent'
    return { state: 'analyzing', textZh: `${agentName} 正在分析…`, textEn: `${agentName} is analyzing…`, active }
  }
  if (latest.type === 'tool.called' || latest.type === 'tool.completed') {
    const agentId = latest.data?.agent_id || tasks.get(latest.task_id)?.agentId
    const agentName = agents.find(agent => agent.id === agentId)?.name || agentId || 'Agent'
    const tool = latest.data?.tool || latest.data?.tool_name || ''
    if (latest.type === 'tool.called') return {
      state: 'working', textZh: `${agentName} 正在调用 ${tool || '工具'}…`,
      textEn: `${agentName} is calling ${tool || 'a tool'}…`, active,
    }
    return {
      state: 'analyzing', textZh: `${agentName} 正在分析工具结果并决定下一步…`,
      textEn: `${agentName} is analyzing the tool result and deciding the next step…`, active,
    }
  }
  if (latest.type === 'task.retry_scheduled') {
    const name = agents.find(agent => agent.id === latest.data?.agent_id)?.name || latest.data?.agent_name || latest.data?.agent_id || 'Agent'
    return { state: 'retrying', textZh: `${name} 正在进行第 ${latest.data?.attempt || '?'} 次尝试…`, textEn: `${name} is starting attempt ${latest.data?.attempt || '?'}…`, active }
  }
  if (active.length > 1) return { state: 'parallel', textZh: `${active.length} 个 Agent 正在并行执行…`, textEn: `${active.length} Agents are running in parallel…`, active }
  if (active.length === 1) return { state: 'working', textZh: `${active[0].agentName} 正在执行${active[0].objective ? `“${active[0].objective}”` : '任务'}…`, textEn: `${active[0].agentName} is working…`, active }
  return { state: 'working', textZh: '正在等待下一阶段…', textEn: 'Waiting for the next stage…', active }
}
