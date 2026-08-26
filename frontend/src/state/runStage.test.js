import test from 'node:test'
import assert from 'node:assert/strict'
import { deriveRunStage } from './runStage.js'

const event = (type, sequence, data = {}, taskId = null) => ({ type, sequence, data, task_id: taskId, timestamp: `2026-08-07T08:00:0${sequence}Z` })

test('describes planning, parallel execution, retry and synthesis stages', () => {
  assert.equal(deriveRunStage([event('host.planning', 1)]).textZh, 'Host 正在分析请求并制定计划…')
  const parallel = deriveRunStage([
    event('host.plan_created', 1, { tasks: [{ id: 'ops' }, { id: 'security' }] }),
    event('task.started', 2, { agent_id: 'ops', agent_name: 'K8s Ops Agent' }, 'ops'),
    event('task.started', 3, { agent_id: 'security', agent_name: 'K8s Security Agent' }, 'security'),
  ], [{ id: 'ops', name: 'K8s Ops Agent' }, { id: 'security', name: 'K8s Security Agent' }])
  assert.equal(parallel.textZh, '2 个 Agent 正在并行执行…')
  assert.equal(parallel.active.length, 2)
  assert.equal(deriveRunStage([...parallel.events || [], event('task.retry_scheduled', 4, { agent_id: 'security', attempt: 2 })], [{ id: 'security', name: 'K8s Security Agent' }]).textZh, 'K8s Security Agent 正在进行第 2 次尝试…')
  assert.equal(deriveRunStage([event('host.synthesis_started', 5)]).textZh, 'Host 正在综合各 Agent 结果…')
})

test('uses terminal run status as the final stage', () => {
  assert.equal(deriveRunStage([event('run.completed', 1)]).state, 'completed')
  assert.equal(deriveRunStage([event('run.failed', 1, { error: 'timeout' })]).textZh, '运行失败：timeout')
})
