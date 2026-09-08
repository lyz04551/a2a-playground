import fs from 'node:fs'
import test from 'node:test'
import assert from 'node:assert/strict'

test('task explorer is reachable from route, navigation, palette, and run trace', () => {
  const files = ['../App.jsx', './shell/AppShell.jsx', './shell/CommandPalette.jsx', './workspace/RunTracePanel.jsx']
    .map(path => fs.readFileSync(new URL(path, import.meta.url), 'utf8'))
  files.forEach(source => assert.match(source, /\/tasks/))
})
