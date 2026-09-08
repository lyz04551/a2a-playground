export function modelConfigPayload(values = {}) {
  return {
    provider: String(values.provider || '').trim(),
    base_url: String(values.base_url || '').trim(),
    model: String(values.model || '').trim(),
    ...(String(values.api_key || '').trim() ? { api_key: String(values.api_key).trim() } : {}),
  }
}

export function modelConfigForm(config = {}) {
  return { provider: config.provider || '', base_url: config.base_url || '', model: config.model || '', api_key: '' }
}
