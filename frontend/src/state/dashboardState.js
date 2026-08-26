export function deriveOnboardingSteps({ modelConfigured = false, agents = [], conversations = [] } = {}) {
  return [
    { id: 'model', complete: Boolean(modelConfigured) },
    { id: 'registered', complete: agents.length > 0 },
    { id: 'online', complete: agents.some(agent => agent.online) },
    { id: 'conversation', complete: conversations.length > 0 },
  ]
}

export function summarizeDashboard({ agents = [], runs = [], approvals = [] } = {}) {
  return {
    agents: agents.length,
    onlineAgents: agents.filter(agent => agent.online).length,
    runs: runs.length,
    completedRuns: runs.filter(run => run.status === 'completed').length,
    pendingApprovals: approvals.filter(approval => approval.status === 'pending').length,
  }
}
