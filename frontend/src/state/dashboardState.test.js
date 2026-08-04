import test from 'node:test'
import assert from 'node:assert/strict'
import { deriveOnboardingSteps, summarizeDashboard } from './dashboardState.js'

test('derives onboarding completion from real system data', () => {
  const steps = deriveOnboardingSteps({
    modelConfigured: true,
    agents: [{ id: 'ops', online: true }],
    conversations: [{ id: 'conversation-1' }],
  })
  assert.deepEqual(steps.map(step => step.complete), [true, true, true, true])
})

test('keeps online registration distinct from agent registration', () => {
  const steps = deriveOnboardingSteps({
    modelConfigured: false,
    agents: [{ id: 'ops', online: false }],
    conversations: [],
  })
  assert.deepEqual(steps.map(step => step.complete), [false, true, false, false])
})

test('summarizes only pending approvals and completed runs', () => {
  const result = summarizeDashboard({
    agents: [{ online: true }, { online: false }],
    runs: [{ status: 'completed' }, { status: 'failed' }],
    approvals: [{ status: 'pending' }, { status: 'approved' }],
  })
  assert.deepEqual(result, { agents: 2, onlineAgents: 1, runs: 2, completedRuns: 1, pendingApprovals: 1 })
})
