export function roundDisplayText(round = {}, zh = false) {
  if (round.reason) return round.reason
  return zh ? '正在分析下一步…' : 'Analyzing the next step…'
}

export function buildRoundTimeline(tasks = [], rounds = []) {
  if (!rounds.length) {
    return tasks.map(task => ({ kind: 'task', id: task.id, task }))
  }
  const byId = new Map(tasks.map(task => [task.id, task]))
  const emitted = new Set()
  const items = []
  for (const round of rounds) {
    items.push({ kind: 'decision', id: `round-${round.round}`, round })
    for (const taskId of round.taskIds || []) {
      const task = byId.get(taskId)
      if (!task) continue
      emitted.add(taskId)
      items.push({ kind: 'task', id: taskId, task })
    }
  }
  for (const task of tasks) {
    if (!emitted.has(task.id)) {
      items.push({ kind: 'task', id: task.id, task })
    }
  }
  return items
}
