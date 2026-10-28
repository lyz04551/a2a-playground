export function normalizeMarkdown(value) {
  if (value == null) return ''
  return String(value).replace(/\\([\\`*{}[\]()#+\-.!_|>])/g, '$1')
}

export function normalizeReportHeadings(value) {
  const lines = String(value ?? '').split('\n')
  let fence = null
  let firstLevel = null
  const headings = []

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/)
    if (fenceMatch) {
      const marker = fenceMatch[1]
      if (!fence) fence = marker
      else if (marker[0] === fence[0] && marker.length >= fence.length) fence = null
      continue
    }
    if (fence) continue
    const heading = line.match(/^( {0,3})(#{1,6})(?=\s|$)(.*)$/)
    if (!heading) continue
    firstLevel ??= heading[2].length
    headings.push({ index, heading })
  }

  if (!firstLevel || firstLevel === 1) return String(value ?? '')
  for (const { index, heading } of headings) {
    const level = Math.min(6, Math.max(1, heading[2].length - firstLevel + 1))
    lines[index] = `${heading[1]}${'#'.repeat(level)}${heading[3]}`
  }
  return lines.join('\n')
}
