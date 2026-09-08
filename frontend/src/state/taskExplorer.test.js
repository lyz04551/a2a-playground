import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTaskFlow, filterTaskRuns, summarizeTaskRun } from './taskExplorer.js'

test('builds Host rounds and Agent children for Auto runs', () => {
  const state = {
    run: { id: 'auto-1', mode: 'auto', status: 'completed' }, hostSummary: '整体检查完成',
    roundOrder: [1], roundsByNumber: { 1: { round: 1, reason: '先检查', taskIds: ['security'] } },
    taskOrder: ['security'], tasksById: { security: { id: 'security', agentId: 'sec', objective: '安全预检', status: 'completed', output: '预检通过', tools: [{ id: 'call-1', name: 'list_k8s_pod', status: 'completed' }] } },
    approvals: [], messages: [], rawEvents: [],
  }
  const nodes = buildTaskFlow(state, [{ id: 'sec', name: 'Security Agent' }])
  assert.deepEqual(nodes.map(node => [node.kind, node.depth]), [['host', 0], ['round', 1], ['agent', 2], ['tool', 3], ['result', 3], ['summary', 1]])
  assert.equal(nodes.at(-1).content, '整体检查完成')
})

test('builds Direct flows without a Host node', () => {
  const state = {
    run: { id: 'direct-1', mode: 'direct', target_agent_id: 'ops' },
    roundOrder: [], roundsByNumber: {}, taskOrder: ['root'],
    tasksById: { root: { id: 'root', agentId: 'ops', status: 'completed' } },
    approvals: [{ id: 'ap-1', taskId: 'root', status: 'approved' }], messages: [], rawEvents: [],
  }
  const nodes = buildTaskFlow(state, [{ id: 'ops', name: 'Ops Agent' }])
  assert.equal(nodes.some(node => node.kind === 'host'), false)
  assert.deepEqual(nodes.map(node => node.kind), ['agent', 'approval'])
})

test('filters and summarizes runs without requiring optional fields', () => {
  const runs = [{ id: 'a', mode: 'auto', status: 'completed', title: 'nginx' }, { id: 'b', mode: 'direct', status: 'failed', target_agent_id: 'ops' }]
  assert.deepEqual(filterTaskRuns(runs, { mode: 'direct', query: 'ops' }).map(run => run.id), ['b'])
  assert.deepEqual(summarizeTaskRun({ run: runs[0], taskOrder: ['x'], tasksById: { x: { tools: [{ id: 't' }] } }, approvals: [{ id: 'ap' }] }), { tasks: 1, agents: 0, tools: 1, approvals: 1 })
})
