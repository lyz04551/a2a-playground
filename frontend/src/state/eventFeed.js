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

export function summarizeEvent(event) {
  const tool = event.payload?.tool || event.payload?.tool_name
  if (event.event_type === 'tool_call' && tool) return `调用工具：${tool}`
  if (event.event_type === 'tool_result' && tool) return `工具完成：${tool}`
  if (event.event_type === 'routing') {
    return `路由至：${event.payload?.agent || event.agent_name || 'Agent'}`
  }
  return event.content || '暂无事件详情'
}
