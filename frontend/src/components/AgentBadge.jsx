import React from 'react'

const agentTones = ['#55d6ad', '#67b7ff', '#f7c66b', '#b89cff', '#ef8cae']

function toneForAgent(id) {
  const hash = [...String(id)].reduce((value, char) => ((value * 31) + char.codePointAt(0)) >>> 0, 0)
  return agentTones[hash % agentTones.length]
}

export default function AgentBadge({ agentId = 'Host Agent', agentName, compact = false }) {
  const color = toneForAgent(agentId || agentName)
  const label = agentName || agentId
  return (
    <span className={`agent-badge ${compact ? 'agent-badge--compact' : ''}`}>
      <i style={{ background: color, boxShadow: `0 0 12px ${color}66` }} />
      {label}
    </span>
  )
}

