export const SETTINGS_STORAGE_KEY = 'a2a-console-settings'

export const DEFAULT_SETTINGS = Object.freeze({
  theme: 'light',
  density: 'comfortable',
  language: 'zh-CN',
  sidebarCollapsed: false,
  onboardingComplete: false,
})

const ALLOWED = {
  theme: new Set(['light', 'dark']),
  density: new Set(['comfortable', 'compact']),
  language: new Set(['zh-CN', 'en-US']),
}

export function normalizeSettings(value) {
  const input = value && typeof value === 'object' ? value : {}
  return {
    theme: ALLOWED.theme.has(input.theme) ? input.theme : DEFAULT_SETTINGS.theme,
    density: ALLOWED.density.has(input.density) ? input.density : DEFAULT_SETTINGS.density,
    language: ALLOWED.language.has(input.language) ? input.language : DEFAULT_SETTINGS.language,
    sidebarCollapsed: typeof input.sidebarCollapsed === 'boolean'
      ? input.sidebarCollapsed
      : DEFAULT_SETTINGS.sidebarCollapsed,
    onboardingComplete: typeof input.onboardingComplete === 'boolean'
      ? input.onboardingComplete
      : DEFAULT_SETTINGS.onboardingComplete,
  }
}

export function parseSettings(rawValue) {
  if (!rawValue) return { ...DEFAULT_SETTINGS }
  try {
    return normalizeSettings(JSON.parse(rawValue))
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function serializeSettings(value) {
  return JSON.stringify(normalizeSettings(value))
}
