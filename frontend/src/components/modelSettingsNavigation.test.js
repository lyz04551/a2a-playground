import fs from 'node:fs'
import test from 'node:test'
import assert from 'node:assert/strict'

test('Host model settings route is placed after Events in navigation', () => {
  const app = fs.readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')
  const shell = fs.readFileSync(new URL('./shell/AppShell.jsx', import.meta.url), 'utf8')
  assert.match(app, /path="\/model-settings"/)
  assert.ok(shell.indexOf("key: '/model-settings'") > shell.indexOf("key: '/events'"))
})
