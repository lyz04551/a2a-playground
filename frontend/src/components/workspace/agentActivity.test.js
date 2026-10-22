import assert from 'node:assert/strict'
import test from 'node:test'
import { recentAgentActivity } from './agentActivity.js'

test('shows real tools from the active Agent in execution order', () => {
  const activity = recentAgentActivity([
    { id: 'old', status: 'completed', tools: [{ id: 'x', name: 'old_tool' }] },
    { id: 'security', agentName: 'K8s Security Agent', status: 'working', tools: [
      { id: 'a', name: 'list_k8s_namespace', status: 'completed', startedAt: '2026-10-22T06:00:00Z' },
      { id: 'b', name: 'get_k8s_resource', status: 'working', startedAt: '2026-10-22T06:00:01Z' },
    ] },
  ])
  assert.deepEqual(activity.map(item => [item.number, item.name, item.status]), [
    [1, 'list_k8s_namespace', 'completed'],
    [2, 'get_k8s_resource', 'working'],
  ])
})
