import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTaskDetails, buildToolDetails, groupToolCalls, statusLabel } from './taskDetails.js'

test('localizes internal execution states without changing their values', () => {
  assert.equal(statusLabel('working', true), '正在执行')
  assert.equal(statusLabel('completed', true), '已完成')
  assert.equal(statusLabel('failed', true), '失败')
  assert.equal(statusLabel('approval_required', true), '等待审批')
  assert.equal(statusLabel('working', false), 'Working')
  assert.equal(statusLabel('custom_state', true), 'custom_state')
})

test('builds readable Agent task details with dependencies and result', () => {
  const tasks = [
    { id: 'ops', agentId: 'ops-agent', label: '检查运行状态', status: 'completed', result: '集群健康' },
    {
      id: 'summary',
      agentId: 'host-agent',
      objective: '综合结论',
      input: '合并检查结果',
      completionCriteria: ['列出优先级'],
      dependsOn: ['ops'],
      status: 'completed',
      result: '整体正常',
      attempt: 2,
      replacedAgentId: 'fallback-agent',
    },
  ]

  const details = buildTaskDetails(tasks[1], tasks, [
    { id: 'host-agent', name: 'Host Worker' },
    { id: 'fallback-agent', name: 'Fallback Worker' },
  ])

  assert.equal(details.agentName, 'Fallback Worker')
  assert.deepEqual(details.dependencies, ['检查运行状态'])
  assert.equal(details.resultText, '整体正常')
  assert.equal(details.attempt, 2)
  assert.deepEqual(details.completionCriteria, ['列出优先级'])
})

test('explains why a working task has no result yet', () => {
  const details = buildTaskDetails(
    { id: 'ops', agentId: 'ops-agent', status: 'working' },
    [],
    [],
  )

  assert.equal(details.resultText, '任务仍在执行，尚未返回结果。')
})

test('builds expandable tool arguments result and error text', () => {
  assert.deepEqual(buildToolDetails({
    arguments: { namespace: 'default' },
    result: { items: 2 },
    error: { message: 'timeout' },
  }), {
    argumentsText: '{\n  "namespace": "default"\n}',
    resultText: '{\n  "items": 2\n}',
    errorText: '{\n  "message": "timeout"\n}',
  })
})

test('groups repeated tools into a compact activity summary', () => {
  const groups = groupToolCalls([
    { id: '1', name: 'list_pods', status: 'completed', durationMs: 120 },
    { id: '2', name: 'list_pods', status: 'working', durationMs: null },
    { id: '3', name: 'get_nodes', status: 'failed', durationMs: 80 },
  ])

  assert.deepEqual(groups.map(group => ({
    name: group.name,
    total: group.total,
    completed: group.completed,
    working: group.working,
    failed: group.failed,
    durationMs: group.durationMs,
  })), [
    { name: 'list_pods', total: 2, completed: 1, working: 1, failed: 0, durationMs: 120 },
    { name: 'get_nodes', total: 1, completed: 0, working: 0, failed: 1, durationMs: 80 },
  ])
})
