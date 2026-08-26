import assert from 'node:assert/strict'
import test from 'node:test'
import { agentHealthView, agentStats, filterAgents } from './agentHealth.js'

test('uses dependency readiness instead of HTTP alone', () => {
  assert.equal(agentHealthView({ online: true, state: 'degraded' }).state, 'degraded')
  assert.equal(agentHealthView({ online: false }).state, 'offline')
  assert.equal(agentHealthView({ online: true, state: 'ready' }).state, 'ready')
})

test('filters agents across identity description and skills', () => {
  const agents = [
    { name: 'K8s Ops', description: 'cluster health', skills: [{ name: 'Nodes', tags: ['kubernetes'] }] },
    { name: 'Security', description: 'RBAC audit', skills: [] },
  ]
  assert.deepEqual(filterAgents(agents, 'kubernetes'), [agents[0]])
  assert.deepEqual(filterAgents(agents, 'rbac'), [agents[1]])
})

test('summarizes registered agent capabilities and readiness', () => {
  const agents = [
    { id: 'ops', capabilities: { streaming: true }, skills: [{ id: 'nodes' }] },
    { id: 'security', capabilities: {}, skills: [{ id: 'rbac' }, { id: 'pods' }] },
  ]
  assert.deepEqual(agentStats(agents, { ops: { online: true, state: 'ready' }, security: { online: true, state: 'degraded' } }), {
    total: 2, streaming: 1, skills: 3, ready: 1, degraded: 1, offline: 0,
  })
})
