export const emptyRunState = {
  status: 'idle',
  steps: [],
  approvals: [],
  artifacts: [],
}

function appendUnique(items, item, key) {
  return items.some(existing => existing[key] === item[key])
    ? items
    : [...items, item]
}

export function reduceRunEvent(state, event) {
  if (!event?.type) return state
  if (event.type === 'routing') {
    const agentId = event.agent_id || event.agent
    const agentName = event.agent || event.agent_id
    return {
      ...state,
      status: 'running',
      steps: appendUnique(state.steps, {
        id: `agent:${agentId}`,
        kind: 'agent',
        agentId,
        agentName,
        label: agentName,
        status: 'working',
      }, 'id'),
    }
  }
  if (event.type === 'tool_call') {
    return {
      ...state,
      status: 'running',
      steps: appendUnique(state.steps, {
        id: event.id,
        kind: 'tool',
        label: event.tool,
        arguments: event.args || {},
        status: 'working',
      }, 'id'),
    }
  }
  if (event.type === 'tool_result') {
    return {
      ...state,
      steps: state.steps.map(step => step.id === event.id
        ? { ...step, status: 'completed', result: event.result }
        : step),
    }
  }
  if (event.type === 'approval_required') {
    const approval = event.approval
    return {
      ...state,
      status: 'approval_required',
      approvals: appendUnique(state.approvals, approval, 'id'),
    }
  }
  if (event.type === 'approval_decided') {
    return {
      ...state,
      status: event.decision === 'approved' ? 'running' : 'completed',
      approvals: state.approvals.map(item => item.id === event.approvalId
        ? { ...item, status: event.decision }
        : item),
    }
  }
  if (event.type === 'artifact') {
    return {
      ...state,
      artifacts: appendUnique(state.artifacts, event, 'id'),
    }
  }
  if (event.type === 'error') return { ...state, status: 'failed' }
  if (event.type === 'done' && state.status !== 'approval_required') {
    return {
      ...state,
      status: 'completed',
      steps: state.steps.map(step => step.status === 'working'
        ? { ...step, status: 'completed' }
        : step),
    }
  }
  return state
}
