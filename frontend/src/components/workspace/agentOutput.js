function formatStructuredResult(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  if (typeof value.status !== 'string' || typeof value.summary !== 'string') return null
  return value.summary.trim() || '本轮 Agent 未生成可展示的检查结论。'
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
  const fences = [...visible.matchAll(/^```(?:coverage|json)?[^\n]*$/gim)]
  if (fences.length % 2) {
    const unfinished = visible.slice(fences.at(-1).index)
    if (/^```(?:coverage|json)[^\n]*\n\s*\{\s*"scope"\s*:/i.test(unfinished)) {
      visible = visible.slice(0, fences.at(-1).index)
    }
  }
  const bareStart = visible.lastIndexOf('\n{')
  if (bareStart >= 0) {
    const candidate = visible.slice(bareStart + 1).trim()
    try {
      if (isCoverage(JSON.parse(candidate))) visible = visible.slice(0, bareStart)
    } catch {
      if (/^\{\s*"scope"\s*:/.test(candidate) && !candidate.endsWith('}')) visible = visible.slice(0, bareStart)
    }
  }
  return visible.trim()
}

export function formatAgentOutput(value) {
  if (value == null || value === '') return ''

  const objectSummary = formatStructuredResult(value)
  if (objectSummary !== null) return objectSummary

  if (typeof value !== 'string') return JSON.stringify(value, null, 2)

  const text = value.trim()
  if (!text.startsWith('{')) return hideCoverageManifest(value)

  try {
    return formatStructuredResult(JSON.parse(text)) ?? hideCoverageManifest(value)
  } catch {
    if (/^\{\s*"/.test(text)) return '正在整理检查结果…'
    return hideCoverageManifest(value)
  }
}
