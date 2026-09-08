const value = (item, camel, snake = camel) => item?.[camel] ?? item?.[snake]

export function filterTaskRuns(runs = [], { mode = 'all', status = 'all', agent = 'all', query = '' } = {}) {
  const needle = query.trim().toLowerCase()
  return runs.filter(run => {
    const runMode = run.mode || 'auto'
    const agentId = value(run, 'targetAgentId', 'target_agent_id') || ''
    const haystack = [run.id, run.title, run.request, agentId, runMode, run.status].join(' ').toLowerCase()
    return (mode === 'all' || runMode === mode)
      && (status === 'all' || run.status === status)
      && (agent === 'all' || agentId === agent)
      && (!needle || haystack.includes(needle))
  })
}

export function summarizeTaskRun(state = {}) {
  const tasks = (state.taskOrder || []).map(id => state.tasksById?.[id]).filter(Boolean)
  return {
    tasks: tasks.length,
    agents: new Set(tasks.map(task => task.agentId).filter(Boolean)).size,
    tools: tasks.reduce((count, task) => count + (task.tools || []).length, 0),
    approvals: (state.approvals || []).length,
  }
}

function agentNode(task, depth, names) {
  return {
    id: `task:${task.id}`, kind: 'agent', depth,
    title: names.get(task.agentId) || task.agentName || task.agentId || 'Agent',
    subtitle: task.objective || task.label || task.id,
    status: task.status || 'queued', data: task,
  }
}

function taskChildren(task, depth, approvals) {
  const nodes = (task.tools || []).map(tool => ({
    id: `tool:${task.id}:${tool.id || tool.name || tool.tool}`, kind: 'tool', depth,
    title: tool.name || tool.tool || 'MCP tool', subtitle: tool.result || tool.error || '',
    status: tool.status || 'working', data: tool,
  }))
  for (const approval of approvals.filter(item => (item.taskId || item.task_id) === task.id)) {
    nodes.push({
      id: `approval:${approval.id}`, kind: 'approval', depth,
      title: approval.tool_name || approval.toolName || 'Human checkpoint',
      subtitle: approval.risk || 'write', status: approval.status || 'pending', data: approval,
    })
  }
  return nodes
}

export function buildTaskFlow(state = {}, agents = []) {
  const run = state.run || {}
  const tasks = (state.taskOrder || []).map(id => state.tasksById?.[id]).filter(Boolean)
  const names = new Map(agents.map(agent => [agent.id, agent.name || agent.id]))
  const approvals = state.approvals || []
  const nodes = []
  const emitted = new Set()
  const addTask = (task, depth) => {
    if (!task || emitted.has(task.id)) return
    emitted.add(task.id)
    nodes.push(agentNode(task, depth, names), ...taskChildren(task, depth + 1, approvals))
  }

  if ((run.mode || 'auto') === 'direct') {
    tasks.forEach(task => addTask(task, 0))
    return nodes
  }

  nodes.push({ id: `host:${run.id || 'run'}`, kind: 'host', depth: 0, title: 'Host Agent', subtitle: run.request || run.title || '', status: run.status || 'working', data: run })
  for (const roundNumber of state.roundOrder || []) {
    const round = state.roundsByNumber?.[roundNumber] || { round: roundNumber }
    nodes.push({ id: `round:${roundNumber}`, kind: 'round', depth: 1, title: `Host 第 ${roundNumber} 轮决策`, subtitle: round.reason || round.response || '', status: round.status || 'completed', data: round })
    ;(round.taskIds || []).forEach(id => addTask(state.tasksById?.[id], 2))
  }
  tasks.forEach(task => addTask(task, 2))
  return nodes
}
