import { formatAgentOutput } from './agentOutput.js'

function printable(value) {
  if (value == null || value === '') return ''
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

export function buildToolDetails(tool = {}) {
  return {
    argumentsText: printable(tool.arguments),
    resultText: printable(tool.result),
    errorText: printable(tool.error),
  }
}

export function groupToolCalls(tools = []) {
  const groups = new Map()
  for (const tool of tools) {
    const name = tool.name || 'Tool call'
    const group = groups.get(name) || {
      name, items: [], total: 0, completed: 0, working: 0, failed: 0, durationMs: 0,
    }
    group.items.push(tool)
    group.total += 1
    if (tool.status === 'completed') group.completed += 1
    else if (tool.status === 'failed') group.failed += 1
    else group.working += 1
    if (Number.isFinite(tool.durationMs)) group.durationMs += tool.durationMs
    groups.set(name, group)
  }
  return [...groups.values()]
}

export function buildTaskDetails(task = {}, tasks = [], agents = []) {
  const effectiveAgentId = task.replacedAgentId || task.agentId
  const agent = agents.find(item => item.id === effectiveAgentId)
  const dependencies = (task.dependsOn || []).map(id => {
    const dependency = tasks.find(item => item.id === id)
    return dependency?.objective || dependency?.label || id
  })
  let resultText = formatAgentOutput(task.result)
  if (!resultText && ['working', 'delegated', 'retrying', 'queued'].includes(task.status)) resultText = '任务仍在执行，尚未返回结果。'
  if (!resultText && task.status === 'failed') resultText = printable(task.error || task.reason) || '任务执行失败。'
  if (!resultText && task.status === 'blocked') resultText = task.blockedReason || task.reason || '任务因依赖不可用而阻塞。'
  if (!resultText && task.status === 'cancelled') resultText = '任务已取消。'
  if (!resultText) resultText = '暂无返回结果。'
  return { ...task, agentName: agent?.name || task.agentName || effectiveAgentId || 'Agent task', effectiveAgentId, objective: task.objective || task.label || 'Agent task', input: printable(task.input), dependencies, completionCriteria: task.completionCriteria || [], attempt: task.attempt || 1, resultText }
}
