import test from 'node:test'
import assert from 'node:assert/strict'
import { modelConfigForm, modelConfigPayload } from './modelConfig.js'

test('blank API key retains the configured Host secret', () => {
  assert.deepEqual(modelConfigPayload({ provider: ' p ', base_url: ' https://example/v1 ', model: ' m ', api_key: ' ' }), {
    provider: 'p', base_url: 'https://example/v1', model: 'm',
  })
})

test('server configuration never populates the secret field', () => {
  assert.deepEqual(modelConfigForm({ provider: 'p', base_url: 'u', model: 'm', api_key: 'leak' }), {
    provider: 'p', base_url: 'u', model: 'm', api_key: '',
  })
})
