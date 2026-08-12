const TERMINAL_TASKS = new Set(['task.completed', 'task.failed', 'task.blocked'])

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
    if (item.type === 'task.started' || item.type === 'task.retry_scheduled') task.active = true
    if (TERMINAL_TASKS.has(item.type)) task.active = false
    tasks.set(item.task_id, task)
  }
  const active = [...tasks.values()].filter(task => task.active).map(task => ({
    ...task,
    agentName: agents.find(agent => agent.id === task.agentId)?.name || task.agentId || 'Agent',
  }))
  if (!latest) return { state: 'idle', textZh: '', textEn: '', active }
  if (latest.type === 'run.completed') return { state: 'completed', textZh: '运行已完成', textEn: 'Run completed', active: [] }
  if (latest.type === 'run.failed') return { state: 'failed', textZh: `运行失败：${latest.data?.error || '原因未知'}`, textEn: `Run failed: ${latest.data?.error || 'unknown error'}`, active: [] }
  if (latest.type === 'run.cancelled') return { state: 'cancelled', textZh: '运行已取消', textEn: 'Run cancelled', active: [] }
  if (latest.type === 'host.planning') return { state: 'planning', textZh: 'Host 正在分析请求并制定计划…', textEn: 'Host is analyzing the request and creating a plan…', active }
  if (latest.type === 'host.plan_created') {
    const count = latest.data?.tasks?.length || 0
    return { state: 'planned', textZh: `已创建 ${count} 个任务…`, textEn: `Created ${count} tasks…`, active }
  }
  if (latest.type === 'host.synthesis_started') return { state: 'synthesizing', textZh: 'Host 正在综合各 Agent 结果…', textEn: 'Host is synthesizing Agent results…', active }
  if (latest.type === 'message.delta') return { state: 'responding', textZh: 'Host 正在生成最终回复…', textEn: 'Host is generating the final response…', active }
  if (latest.type === 'task.retry_scheduled') {
    const name = agents.find(agent => agent.id === latest.data?.agent_id)?.name || latest.data?.agent_name || latest.data?.agent_id || 'Agent'
    return { state: 'retrying', textZh: `${name} 正在进行第 ${latest.data?.attempt || '?'} 次尝试…`, textEn: `${name} is starting attempt ${latest.data?.attempt || '?'}…`, active }
  }
  if (active.length > 1) return { state: 'parallel', textZh: `${active.length} 个 Agent 正在并行执行…`, textEn: `${active.length} Agents are running in parallel…`, active }
  if (active.length === 1) return { state: 'working', textZh: `${active[0].agentName} 正在执行${active[0].objective ? `“${active[0].objective}”` : '任务'}…`, textEn: `${active[0].agentName} is working…`, active }
  return { state: 'working', textZh: '正在等待下一阶段…', textEn: 'Waiting for the next stage…', active }
}
