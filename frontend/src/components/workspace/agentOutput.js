function extractSummary(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  return typeof value.summary === 'string' ? value.summary.trim() : ''
}

const COVERAGE_FIELDS = ['scope', 'expected_targets', 'inspected_targets', 'enumeration_complete', 'evidence_call_ids']

function isCoverage(value) {
  return value && typeof value === 'object' && COVERAGE_FIELDS.every(field => Object.hasOwn(value, field))
}

export function hideCoverageManifest(value) {
  if (typeof value !== 'string') return value
  let visible = value.replace(/```(?:coverage|json)?[ \t]*\n([\s\S]*?)\n```/gi, (block, body) => {
    try { return isCoverage(JSON.parse(body)) ? '' : block } catch { return block }
  })
  const bareStart = visible.lastIndexOf('\n{')
  if (bareStart >= 0) {
    try {
      if (isCoverage(JSON.parse(visible.slice(bareStart + 1)))) visible = visible.slice(0, bareStart)
    } catch {
      if (!visible.slice(bareStart).trimEnd().endsWith('}')) visible = visible.slice(0, bareStart)
    }
  }
  const fences = [...visible.matchAll(/^```(?:coverage|json)?[^\n]*$/gim)]
  if (fences.length % 2) visible = visible.slice(0, fences.at(-1).index)
  return visible.trim()
}

export function formatAgentOutput(value) {
  if (value == null || value === '') return ''

  const objectSummary = extractSummary(value)
  if (objectSummary) return objectSummary

  if (typeof value !== 'string') return JSON.stringify(value, null, 2)

  const text = value.trim()
  if (!text.startsWith('{')) return hideCoverageManifest(value)

  try {
    return extractSummary(JSON.parse(text)) || hideCoverageManifest(value)
  } catch {
    return hideCoverageManifest(value)
  }
}
