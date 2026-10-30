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

export function isStreamingReport(content = '') {
  return /^\s{0,3}#{1,6}\s+[^\n]*(?:报告|审计结果|检查结果|检查结论|report|findings|assessment|summary)[^\n]*$/im.test(content)
}

export function visibleConversationMessages(messages = [], loading = false) {
  return messages.filter(message => !message.progress && (message.completed !== false || isStreamingReport(message.content)))
}
