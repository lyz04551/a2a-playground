export function groupAgentDrafts(messages = []) {
  const drafts = new Map()
  for (const message of messages) {
    if (message.progress && message.taskId) drafts.set(message.taskId, message)
  }
  const attached = new Set()
  const grouped = messages.map(message => {
    if (message.progress || !message.taskId || !drafts.has(message.taskId)) return message
    attached.add(message.taskId)
    return { ...message, draftContent: drafts.get(message.taskId).content }
  })
  return grouped.filter(message => !message.progress || !attached.has(message.taskId))
}
