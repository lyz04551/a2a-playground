import React from 'react'

const agentTone = {
  'k8s-ops': '#55d6ad',
  'k8s-orchestrator': '#67b7ff',
  'k8s-security': '#f7c66b',
  'Host Agent': '#b89cff',
}

export default function AgentBadge({ agentId = 'Host Agent', agentName, compact = false }) {
  const color = agentTone[agentId] || (agentName && agentTone[agentName]) || '#8ca3bd'
  const label = agentName || agentId
  return (
    <span className={`agent-badge ${compact ? 'agent-badge--compact' : ''}`}>
      <i style={{ background: color, boxShadow: `0 0 12px ${color}66` }} />
      {label}
    </span>
  )
}

