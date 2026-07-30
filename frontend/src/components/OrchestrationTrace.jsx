import React from 'react'
import { CheckCircleFilled, ClockCircleFilled, CloseCircleFilled, LoadingOutlined } from '@ant-design/icons'
import AgentBadge from './AgentBadge'
import ApprovalCard from './ApprovalCard'
import ArtifactCard from './ArtifactCard'

function StatusIcon({ status }) {
  if (status === 'completed') return <CheckCircleFilled className="trace-ok" />
  if (status === 'failed') return <CloseCircleFilled className="trace-failed" />
  if (status === 'working') return <LoadingOutlined className="trace-working" />
  return <ClockCircleFilled className="trace-waiting" />
}

export default function OrchestrationTrace({ run, onApproval }) {
  const hostStatus = run.status === 'idle'
    ? 'queued'
    : run.status === 'completed'
      ? 'completed'
      : run.status === 'failed'
        ? 'failed'
        : 'working'

  return (
    <aside className="orchestration-trace">
      <header>
        <div>
          <span className="trace-kicker">Live orchestration</span>
          <h3>Agent trace</h3>
        </div>
        <span className={`run-state run-state--${run.status}`}>{run.status}</span>
      </header>

      <div className="trace-host">
        <StatusIcon status={hostStatus} />
        <div><AgentBadge /><small>动态规划与用户节奏</small></div>
      </div>

      <div className="trace-list">
        {run.steps.length === 0 && (
          <p className="trace-empty">Host 的 A2A 路由、工具调用和审批会实时出现在这里。</p>
        )}
        {run.steps.map(step => (
          <div className="trace-step" key={step.id}>
            <StatusIcon status={step.status} />
            <div>
              {step.kind === 'agent'
                ? <AgentBadge agentId={step.agentId} agentName={step.agentName} compact />
                : <strong>{step.label}</strong>}
              {step.arguments && Object.keys(step.arguments).length > 0 && (
                <code>{JSON.stringify(step.arguments)}</code>
              )}
            </div>
          </div>
        ))}
      </div>

      {run.approvals.map(approval => (
        <ApprovalCard
          key={approval.id}
          approval={approval}
          onDecide={onApproval}
        />
      ))}
      {run.artifacts.map(artifact => (
        <ArtifactCard key={artifact.id} artifact={artifact} />
      ))}
    </aside>
  )
}
