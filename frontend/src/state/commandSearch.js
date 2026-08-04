function searchable(value) {
  return String(value || '').toLocaleLowerCase()
}

function scoreCommand(command, query) {
  if (!query) return 1
  const title = searchable(command.title)
  const subtitle = searchable(command.subtitle)
  const keywords = (command.keywords || []).map(searchable)
  if (title === query) return 140
  if (title.startsWith(query)) return 120
  if (title.includes(query)) return 100
  if (subtitle.includes(query)) return 50
  if (keywords.some(keyword => keyword.includes(query))) return 25
  return 0
}

export function searchCommands(commands = [], query = '', { type = '', limit = 12 } = {}) {
  const normalizedQuery = searchable(query.trim())
  return commands
    .map((command, index) => ({ command, index, score: scoreCommand(command, normalizedQuery) }))
    .filter(item => (!type || item.command.type === type) && item.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .slice(0, limit)
    .map(item => item.command)
}
