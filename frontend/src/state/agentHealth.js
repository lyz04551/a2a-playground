export function agentHealthView(health) {
  if (!health?.online) return { state: health ? 'offline' : 'unknown', tone: 'default' }
  if (health.state === 'ready') return { state: 'ready', tone: 'success' }
  return { state: 'degraded', tone: 'warning' }
}

export function filterAgents(agents, query = '') {
  const needle = query.trim().toLowerCase()
  if (!needle) return agents
  return agents.filter(agent => [
    agent.name,
    agent.description,
    ...(agent.skills || []).flatMap(skill => [skill.name, skill.id, ...(skill.tags || [])]),
  ].some(value => String(value || '').toLowerCase().includes(needle)))
}

export function agentStats(agents, healthMap = {}) {
  const states = agents.map(agent => agentHealthView(healthMap[agent.id]).state)
  return {
    total: agents.length,
    streaming: agents.filter(agent => agent.capabilities?.streaming).length,
    skills: agents.reduce((total, agent) => total + (agent.skills?.length || 0), 0),
    ready: states.filter(state => state === 'ready').length,
    degraded: states.filter(state => state === 'degraded').length,
    offline: states.filter(state => state === 'offline').length,
  }
}
