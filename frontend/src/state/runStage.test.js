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
  assert.equal(deriveRunStage([event('run.partial', 1)]).textZh, '部分完成：仍有检查缺少充分证据')
  assert.equal(deriveRunStage([event('run.evidence_insufficient', 1)]).state, 'evidence_insufficient')
  assert.equal(deriveRunStage([event('run.failed', 1, { error: 'timeout' })]).textZh, '运行失败：timeout')
})

test('keeps the Agent stage while its message streams before tool calls finish', () => {
  const agents = [{ id: 'ops', name: 'K8s Ops Agent' }]
  const events = [
    event('host.plan_created', 1, { tasks: [{ id: 'inspect', agent_id: 'ops' }] }),
    event('task.started', 2, { agent_id: 'ops' }, 'inspect'),
    event('message.delta', 3, { agent_id: 'ops', delta: '现在获取列表' }, 'inspect'),
  ]
  assert.equal(deriveRunStage(events, agents).textZh, 'K8s Ops Agent 正在生成回复…')
  assert.equal(deriveRunStage([...events, event('task.completed', 4, {}, 'inspect'), event('message.delta', 5)]).textZh, 'Host 正在生成最终回复…')
})

test('direct Agent streaming uses event ownership without a task.started event', () => {
  const events = [
    event('run.started', 1, { mode: 'direct', target_agent_id: 'ops' }),
    event('task.delegated', 2, { agent_id: 'ops' }, 'root'),
    event('message.delta', 3, { agent_id: 'ops', content: '正在检查' }, 'root'),
  ]
  const agents = [{ id: 'ops', name: 'K8s Ops Agent' }]
  const stage = deriveRunStage(events, agents)
  assert.equal(stage.textZh, 'K8s Ops Agent 正在生成回复…')
  assert.equal(stage.active[0].agentName, 'K8s Ops Agent')
  assert.equal(deriveRunStage([...events, event('task.completed', 4, {}, 'root')], agents).active.length, 0)
})

test('names the live tool and the subsequent model analysis phase', () => {
  const agents = [{ id: 'security', name: 'K8s Security Agent' }]
  const started = [
    event('task.started', 1, { agent_id: 'security' }, 'audit'),
    event('tool.called', 2, { agent_id: 'security', tool: 'get_k8s_resource' }, 'audit'),
  ]
  assert.equal(deriveRunStage(started, agents).textZh, 'K8s Security Agent 正在调用 get_k8s_resource…')
  assert.equal(deriveRunStage([...started, event('tool.completed', 3, { agent_id: 'security', tool: 'get_k8s_resource' }, 'audit')], agents).textZh, 'K8s Security Agent 正在分析工具结果并决定下一步…')
  assert.equal(deriveRunStage([...started, event('agent.thinking_delta', 3, { agent_id: 'security', content: '分析中' }, 'audit')], agents).textZh, 'K8s Security Agent 正在分析…')
})
