import assert from 'node:assert/strict'
import test from 'node:test'
import { agentPromptTemplates } from './promptTemplates.js'

test('starter tasks follow registered Agent card examples', () => {
  const templates = agentPromptTemplates([{ id: 'custom', name: 'Custom Agent', skills: [
    { id: 'inspect', name: 'Inspect things', examples: ['Check object alpha.', '  '] },
  ] }])
  assert.deepEqual(templates, [{
    id: 'custom:inspect:0', title: 'Inspect things', description: 'Custom Agent', prompt: 'Check object alpha.',
  }])
  assert.deepEqual(agentPromptTemplates([]), [])
  assert.equal(agentPromptTemplates([{ id: 'custom', skills: [{ id: 'inspect', examples: ['Check object alpha.'] }] }], 'zh-CN')[0].prompt, '请用中文回答：Check object alpha.')
})
