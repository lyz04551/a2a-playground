import React from 'react'
import { BugOutlined, LoadingOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import SystemStatus from './SystemStatus'
import RunTimeline from './RunTimeline'

export default function RunTracePanel({ run = {}, loading = false, error, onApproval, onArtifactOpen, onDebug }) {
  const tasks = run.tasks || run.steps || []
  const approvals = run.approvals || []
  const artifacts = run.artifacts || []
  return (
    <aside className="workspace-trace" aria-label="Run trace">
      <header><div><span className="workspace-eyebrow">Execution</span><h2>Run trace</h2></div><div className="workspace-trace__actions"><SystemStatus status={{ state: run.status || 'online' }} /><Button type="text" size="small" aria-label="Open run debugger" icon={<BugOutlined />} onClick={onDebug} /></div></header>
      {loading && <p className="workspace-state" role="status"><LoadingOutlined /> Awaiting run events…</p>}
      {error && <p className="workspace-state workspace-state--error" role="alert">{error}</p>}
      {!loading && !error && tasks.length === 0 && <p className="workspace-empty">Run activity will appear here.</p>}
      <RunTimeline run={run} tasks={tasks} />
      {approvals.map(approval => <section className="workspace-approval" key={approval.id}><SafetyCertificateOutlined aria-hidden="true" /><div><strong>Approval required</strong><p>{approval.tool_name || approval.toolName || 'This operation'} needs your confirmation.</p><button type="button" onClick={() => onApproval?.(approval, 'approved')}>Approve</button><button type="button" onClick={() => onApproval?.(approval, 'rejected')}>Reject</button></div></section>)}
      {artifacts.length > 0 && <section className="workspace-artifacts"><span className="workspace-eyebrow">Artifacts</span>{artifacts.map(artifact => <button type="button" key={artifact.id} onClick={() => onArtifactOpen?.(artifact)}>{artifact.name || artifact.id}</button>)}</section>}
    </aside>
  )
}
