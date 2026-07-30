import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyRunState, reduceRunEvent } from './runEvents.js'

test('routing and tool events build an ordered orchestration trace', () => {
  const routed = reduceRunEvent(emptyRunState, {
    type: 'routing',
    agent_id: 'k8s-ops',
  })
  const called = reduceRunEvent(routed, {
    type: 'tool_call',
    id: 'call-1',
    tool: 'get_k8s_pod_logs',
    args: { name: 'api' },
  })
  const completed = reduceRunEvent(called, {
    type: 'tool_result',
    id: 'call-1',
    result: 'logs',
  })

  assert.deepEqual(
    completed.steps.map(step => [step.id, step.status]),
    [
      ['agent:k8s-ops', 'working'],
      ['call-1', 'completed'],
    ],
  )
})

test('duplicate SSE events do not duplicate trace entries', () => {
  const event = {
    type: 'tool_call',
    id: 'call-1',
    tool: 'get_k8s_pod_logs',
  }
  const once = reduceRunEvent(emptyRunState, event)
  const twice = reduceRunEvent(once, event)

  assert.equal(twice.steps.length, 1)
})

test('done completes all still-working trace steps', () => {
  let state = reduceRunEvent(emptyRunState, {
    type: 'routing',
    agent_id: 'k8s-ops',
  })
  state = reduceRunEvent(state, {
    type: 'tool_call',
    id: 'call-1',
    tool: 'send_task',
  })

  const finished = reduceRunEvent(state, { type: 'done' })

  assert.equal(finished.status, 'completed')
  assert.deepEqual(
    finished.steps.map(step => step.status),
    ['completed', 'completed'],
  )
})

test('approval holds run until a human decision', () => {
  const pending = reduceRunEvent(emptyRunState, {
    type: 'approval_required',
    approval: { id: 'ap-1', status: 'pending' },
  })
  const approved = reduceRunEvent(pending, {
    type: 'approval_decided',
    approvalId: 'ap-1',
    decision: 'approved',
  })

  assert.equal(pending.status, 'approval_required')
  assert.equal(approved.status, 'running')
  assert.equal(approved.approvals[0].status, 'approved')
})
