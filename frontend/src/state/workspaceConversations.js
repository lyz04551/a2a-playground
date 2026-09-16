export function filterConversations(conversations = [], query = '') {
  const needle = query.trim().toLocaleLowerCase()
  if (!needle) return conversations
  return conversations.filter(conversation => [
    conversation.title,
    conversation.agent_name,
    conversation.agentName,
    conversation.id,
  ].some(value => String(value || '').toLocaleLowerCase().includes(needle)))
}

export function normalizeConversationTitle(value) {
  return String(value || '').trim().slice(0, 80)
}

export function workspaceConversationSearch(search = '', conversationId = '') {
  const params = new URLSearchParams(search)
  params.delete('prompt')
  params.delete('new')
  if (conversationId) params.set('conversation', conversationId)
  else params.delete('conversation')
  return params.toString()
}
