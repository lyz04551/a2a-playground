const views = {
  ok: ['正常', 'Healthy', 'success'],
  error: ['异常', 'Failed', 'error'],
  offline: ['离线', 'Offline', 'error'],
  unsupported: ['不支持', 'Unsupported', 'default'],
  testing: ['测试中', 'Testing', 'processing'],
  unknown: ['未测试', 'Not tested', 'default'],
}

export function diagnosticView(result, language = 'zh-CN') {
  const state = result?.state || 'unknown'
  const [zh, en, color] = views[state] || views.unknown
  return {
    label: language === 'zh-CN' ? zh : en,
    color,
    latency: Number.isFinite(result?.latency_ms) ? `${result.latency_ms} ms` : '',
    error: String(result?.error || '').slice(0, 200),
  }
}
