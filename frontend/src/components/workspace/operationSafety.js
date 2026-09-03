const SENSITIVE_KEY = /(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|credential)/i

export function redactSensitive(value, seen = new WeakSet()) {
  if (Array.isArray(value)) return value.map(item => redactSensitive(item, seen))
  if (!value || typeof value !== 'object') return value
  if (seen.has(value)) return '[Circular]'
  seen.add(value)
  const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key,
    SENSITIVE_KEY.test(key) ? '[REDACTED]' : redactSensitive(item, seen),
  ]))
  seen.delete(value)
  return result
}

function flatten(value, prefix = '', target = {}) {
  if (!value || typeof value !== 'object') {
    target[prefix || 'value'] = value
    return target
  }
  const entries = Array.isArray(value) ? value.entries() : Object.entries(value)
  for (const [key, item] of entries) {
    const path = prefix ? `${prefix}.${key}` : String(key)
    if (item && typeof item === 'object') flatten(item, path, target)
    else target[path] = item
  }
  return target
}

export function diffArguments(previous = {}, current = {}) {
  const before = flatten(redactSensitive(previous))
  const after = flatten(redactSensitive(current))
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .sort()
    .flatMap(path => {
      if (!(path in before)) return [{ path, kind: 'added', before: undefined, after: after[path] }]
      if (!(path in after)) return [{ path, kind: 'removed', before: before[path], after: undefined }]
      if (JSON.stringify(before[path]) !== JSON.stringify(after[path])) return [{ path, kind: 'changed', before: before[path], after: after[path] }]
      return []
    })
}

export function formatArgumentValue(value) {
  if (value === undefined) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function approvalRisk(approval = {}) {
  const explicit = approval.risk || approval.risk_level || approval.riskLevel
  if (explicit) return String(explicit).toLowerCase()
  const tool = String(approval.tool_name || approval.toolName || '').toLowerCase()
  return /delete|drain|force|exec|remove|uninstall/.test(tool) ? 'critical' : 'write'
}
