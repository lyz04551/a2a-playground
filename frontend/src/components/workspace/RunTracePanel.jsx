import React, { useMemo, useState } from 'react'
import { BugOutlined, LoadingOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Drawer, Tag } from 'antd'
import SystemStatus from './SystemStatus'
import RunTimeline from './RunTimeline'
import { buildTaskDetails } from './taskDetails'
import ApprovalCard from '../ApprovalCard'

export default function RunTracePanel({ run = {}, stage, agents = [], language = 'en-US', loading = false, error, canCancel = false, cancelling = false, onCancel, onApproval, onArtifactOpen, onDebug }) {
  const zh = language.startsWith('zh')
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const tasks = run.tasks || run.steps || []
  const selectedTask = tasks.find(task => task.id === selectedTaskId)
  const details = useMemo(() => selectedTask ? buildTaskDetails(selectedTask, tasks, agents) : null, [selectedTask, tasks, agents])
  const approvals = run.approvals || []
  const previousMatchingApproval = (approval, index) => [...approvals.slice(0, index)].reverse().find(candidate => (candidate.agent_id || candidate.agentId) === (approval.agent_id || approval.agentId) && (candidate.tool_name || candidate.toolName) === (approval.tool_name || approval.toolName))
  const enrichedApprovals = approvals.map((approval, index) => ({
    ...approval,
    previousApproval: previousMatchingApproval(approval, index),
  }))
  const unlinkedApprovals = enrichedApprovals.filter(approval => !(approval.taskId || approval.task_id))
  const artifacts = run.artifacts || []
  const stageText = zh ? stage?.textZh : stage?.textEn
  const failureDetail = stage?.state === 'failed'
    ? stageText?.replace(/^(运行失败：|Run failed:\s*)/, '')
    : ''
  return (
    <aside className="workspace-trace" aria-label="Run trace">
      <header><div><span className="workspace-eyebrow">Execution</span><h2>Run trace</h2></div><div className="workspace-trace__actions"><SystemStatus status={{ state: run.status || 'online' }} />{canCancel && <Button danger size="small" loading={cancelling} aria-label={zh ? '停止当前运行' : 'Stop current run'} icon={<StopOutlined />} onClick={onCancel}>{zh ? '停止' : 'Stop'}</Button>}<Button type="text" size="small" aria-label="Open run debugger" icon={<BugOutlined />} onClick={onDebug} /></div></header>
      {stage?.textZh && <section className={`run-stage is-${stage.state || 'working'}`}><strong>{stage?.state === 'failed' ? (zh ? '运行失败' : 'Run failed') : stageText}</strong>{failureDetail && <details><summary>{zh ? '查看失败原因' : 'View failure reason'}</summary><p>{failureDetail}</p></details>}{stage.active?.map(item => <small key={item.id}>{item.agentName}{item.objective ? ` · ${item.objective}` : ''}</small>)}</section>}
      {loading && <p className="workspace-state" role="status"><LoadingOutlined /> Awaiting run events…</p>}
      {error && <p className="workspace-state workspace-state--error" role="alert">{error}</p>}
      {!loading && !error && tasks.length === 0 && <p className="workspace-empty">Run activity will appear here.</p>}
      <RunTimeline run={run} tasks={tasks} rounds={run.rounds || []} approvals={enrichedApprovals} onApproval={onApproval} selectedTaskId={selectedTaskId} onTaskSelect={task => setSelectedTaskId(task.id)} language={language} />
      {unlinkedApprovals.map(approval => <ApprovalCard key={approval.id} approval={approval} previousApproval={approval.previousApproval} language={language} onDecide={onApproval} />)}
      {artifacts.length > 0 && <section className="workspace-artifacts"><span className="workspace-eyebrow">Artifacts</span>{artifacts.map(artifact => <button type="button" key={artifact.id} onClick={() => onArtifactOpen?.(artifact)}>{artifact.name || artifact.id}</button>)}</section>}
      <Drawer title={zh ? 'Agent 任务详情' : 'Agent task details'} open={Boolean(details)} onClose={() => setSelectedTaskId(null)} width={520}>
        {details && <div className="task-details"><h3>{details.objective}</h3> <Tag>{details.status || 'queued'}</Tag><dl><dt>Agent</dt><dd>{details.agentName}<small>{details.effectiveAgentId}</small></dd><dt>{zh ? '输入' : 'Input'}</dt><dd>{details.input || '—'}</dd><dt>{zh ? '依赖' : 'Dependencies'}</dt><dd>{details.dependencies.length ? details.dependencies.join(' → ') : (zh ? '无' : 'None')}</dd><dt>{zh ? '尝试次数' : 'Attempt'}</dt><dd>{details.attempt}{details.maxAttempts ? ` / ${details.maxAttempts}` : ''}</dd><dt>{zh ? '完成标准' : 'Completion criteria'}</dt><dd>{details.completionCriteria.length ? <ul>{details.completionCriteria.map(item => <li key={item}>{item}</li>)}</ul> : '—'}</dd></dl><section><strong>{zh ? '返回结果' : 'Result'}</strong><pre>{details.resultText}</pre></section></div>}
      </Drawer>
    </aside>
  )
}
