import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULT_SETTINGS,
  normalizeSettings,
  parseSettings,
  serializeSettings,
} from './consoleSettings.js'

test('normalizes persisted console settings', () => {
  assert.deepEqual(normalizeSettings({ theme: 'dark', density: 'compact' }), {
    ...DEFAULT_SETTINGS,
    theme: 'dark',
    density: 'compact',
  })
})

test('replaces unsupported persisted values with defaults', () => {
  assert.deepEqual(normalizeSettings({ theme: 'neon', language: 'fr', sidebarCollapsed: 'yes' }), DEFAULT_SETTINGS)
})

test('parses valid JSON and recovers from invalid storage', () => {
  assert.equal(parseSettings('{broken').theme, DEFAULT_SETTINGS.theme)
  assert.equal(parseSettings('{"language":"en-US"}').language, 'en-US')
})

test('serializes only supported settings', () => {
  const serialized = JSON.parse(serializeSettings({ ...DEFAULT_SETTINGS, theme: 'dark', extra: true }))
  assert.equal(serialized.theme, 'dark')
  assert.equal(serialized.extra, undefined)
})
