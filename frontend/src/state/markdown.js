export function normalizeMarkdown(value) {
  if (value == null) return ''
  return String(value).replace(/\\([\\`*{}[\]()#+\-.!_|>])/g, '$1')
}
