const ACTIVE_TASK_STATES = new Set(['working', 'delegated', 'running'])

export function recentAgentActivity(tasks = [], limit = 4) {
  const active = tasks.filter(task => ACTIVE_TASK_STATES.has(task.status))
  const source = active.length ? active : tasks.slice(-1)
  return source.flatMap(task => (task.tools || []).map((tool, index) => ({
    id: `${task.id}:${tool.id || index}`,
    agentName: task.agentName || task.agentId || 'Agent',
    name: tool.name || 'Tool',
    status: tool.status || 'working',
    number: index + 1,
    startedAt: tool.startedAt || '',
  }))).sort((a, b) => a.startedAt.localeCompare(b.startedAt) || a.number - b.number).slice(-limit)
}
