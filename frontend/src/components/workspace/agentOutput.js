function extractSummary(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  return typeof value.summary === 'string' ? value.summary.trim() : ''
}

export function formatAgentOutput(value) {
  if (value == null || value === '') return ''

  const objectSummary = extractSummary(value)
  if (objectSummary) return objectSummary

  if (typeof value !== 'string') return JSON.stringify(value, null, 2)

  const text = value.trim()
  if (!text.startsWith('{')) return value

  try {
    return extractSummary(JSON.parse(text)) || value
  } catch {
    return value
  }
}
