import assert from 'node:assert/strict'
import test from 'node:test'
import { PROMPT_TEMPLATES } from './promptTemplates.js'

test('the five quick start tasks keep their Chinese labels and prompts', () => {
  assert.equal(PROMPT_TEMPLATES.length, 5)
  assert.deepEqual(PROMPT_TEMPLATES.map(task => task.id), [
    'cluster-health', 'pod-analysis', 'security-scan', 'event-triage', 'deployment-review',
  ])
  assert.ok(PROMPT_TEMPLATES.every(task => task.title['zh-CN'] && task.prompt))
})
