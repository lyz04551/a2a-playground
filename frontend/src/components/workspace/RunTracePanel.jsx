import React, { useEffect, useMemo, useState } from 'react'
import { BranchesOutlined, BugOutlined, LoadingOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Drawer, Tag } from 'antd'
import { useNavigate } from 'react-router-dom'
import SystemStatus from './SystemStatus'
import RunTimeline from './RunTimeline'
import { buildTaskDetails, statusLabel } from './taskDetails'
import ApprovalCard from '../ApprovalCard'
import MarkdownContent from '../MarkdownContent'
import { formatAgentOutput } from './agentOutput'
import { getCoveragePresentation } from './workspaceState'

export default function RunTracePanel({ run = {}, stage, agents = [], language = 'en-US', loading = false, error, canCancel = false, cancelling = false, onCancel, onApproval, onArtifactOpen, onDebug }) {
  const zh = language.startsWith('zh')
  const navigate = useNavigate()
  const [selectedTaskId, setSelectedTaskId] = useState(null)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!loading) return undefined
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [loading])
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
  const latestEvent = run.rawEvents?.at(-1)
  const elapsed = latestEvent?.timestamp ? Math.max(0, Math.floor((now - Date.parse(latestEvent.timestamp)) / 1000)) : 0
  const waitingForAgent = latestEvent?.type === 'tool.completed'
  const waitingText = waitingForAgent
    ? (zh ? `工具结果已返回，Agent 正在分析并决定下一步 · 已等待 ${elapsed} 秒` : `Tool results received. Agent is analyzing the next step · ${elapsed}s`)
    : (zh ? `正在等待下一条运行事件 · 已等待 ${elapsed} 秒` : `Awaiting the next run event · ${elapsed}s`)
  const coverage = getCoveragePresentation(tasks)
  return (
    <aside className="workspace-trace" aria-label="Run trace">
      <header><div><span className="workspace-eyebrow">Execution</span><h2>Run trace</h2></div><div className="workspace-trace__actions"><SystemStatus status={{ state: run.status || 'online' }} />{run.id && <Button type="text" size="small" aria-label={zh ? '打开完整任务流' : 'Open full task flow'} icon={<BranchesOutlined />} onClick={() => navigate(`/tasks?run=${encodeURIComponent(run.id)}`)} />}{canCancel && <Button danger size="small" loading={cancelling} aria-label={zh ? '停止当前运行' : 'Stop current run'} icon={<StopOutlined />} onClick={onCancel}>{zh ? '停止' : 'Stop'}</Button>}<Button type="text" size="small" aria-label="Open run debugger" icon={<BugOutlined />} onClick={onDebug} /></div></header>
      {stage?.textZh && <section className={`run-stage is-${stage.state || 'working'}`}><strong>{stage?.state === 'failed' ? (zh ? '运行失败' : 'Run failed') : stageText}</strong>{failureDetail && <details><summary>{zh ? '查看失败原因' : 'View failure reason'}</summary><p>{failureDetail}</p></details>}{stage.active?.map(item => <small key={item.id}>{item.agentName}{item.objective ? ` · ${item.objective}` : ''}</small>)}</section>}
      {loading && <p className="workspace-state" role="status"><LoadingOutlined /> {waitingText}</p>}
      {error && <p className="workspace-state workspace-state--error" role="alert">{error}</p>}
      {coverage && <section className={`workspace-coverage ${coverage.complete ? 'is-complete' : 'is-incomplete'}`} aria-label={zh ? '逐项检查范围' : 'Itemized review coverage'}>
        <div className="workspace-coverage__heading"><strong>{zh ? '逐项检查' : 'Itemized review'}</strong>{coverage.enumerationComplete && coverage.total > 0 && <span>{coverage.checked}/{coverage.total}</span>}</div>
        <p>{coverage.complete ? (zh ? '计划内目标均已验证' : 'All planned targets verified') : coverage.enumerationComplete ? (zh ? `还有 ${coverage.missing.length} 项未验证` : `${coverage.missing.length} targets remain unverified`) : (zh ? '目标清单尚未确认，暂不计算完成比例' : 'Target list is not confirmed; no completion ratio yet')}</p>
        {coverage.enumerationComplete && coverage.total > 0 && <div className="workspace-coverage__bar" role="progressbar" aria-valuenow={coverage.checked} aria-valuemin={0} aria-valuemax={coverage.total}><i style={{ width: `${Math.round(coverage.checked / coverage.total * 100)}%` }} /></div>}
        {!!coverage.missing.length && <details><summary>{zh ? '查看未验证目标' : 'Show unverified targets'}</summary><ul>{coverage.missing.map(target => <li key={target}>{target}</li>)}</ul></details>}
      </section>}
      {!loading && !error && tasks.length === 0 && <p className="workspace-empty">Run activity will appear here.</p>}
      <RunTimeline run={run} tasks={tasks} rounds={run.rounds || []} approvals={enrichedApprovals} onApproval={onApproval} selectedTaskId={selectedTaskId} onTaskSelect={task => setSelectedTaskId(task.id)} language={language} now={now} />
      {unlinkedApprovals.map(approval => <ApprovalCard key={approval.id} approval={approval} previousApproval={approval.previousApproval} language={language} onDecide={onApproval} />)}
      {artifacts.length > 0 && <section className="workspace-artifacts"><span className="workspace-eyebrow">Artifacts</span>{artifacts.map(artifact => <button type="button" key={artifact.id} onClick={() => onArtifactOpen?.(artifact)}>{artifact.name || artifact.id}</button>)}</section>}
      <Drawer title={zh ? 'Agent 任务详情' : 'Agent task details'} open={Boolean(details)} onClose={() => setSelectedTaskId(null)} width={520}>
        {details && <div className="task-details">
          <div className="task-details__heading"><h3>{details.objective}</h3><Tag>{statusLabel(details.status || 'queued', zh)}</Tag><small>{details.agentName}</small></div>
          <section className="task-details__report"><strong>{zh ? '返回结果' : 'Result'}</strong><MarkdownContent>{formatAgentOutput(details.resultText)}</MarkdownContent></section>
          {details.assessment && <section className="task-evidence"><strong>{zh ? '证据分类' : 'Evidence classification'}</strong>
            <p>{zh ? '已验证工具结果' : 'Observed tool results'}: {details.assessment.facts?.length || 0}</p>
            {!!details.assessment.inferences?.length && <p>{zh ? '推断' : 'Inferences'}: {details.assessment.inferences.length}</p>}
            {!!details.assessment.unknowns?.length && <><strong>{zh ? '仍未知' : 'Still unknown'}</strong><ul>{details.assessment.unknowns.map((item, index) => <li key={`${item.resource_id || 'unknown'}-${index}`}>{item.resource_id || '—'} · {item.reason}</li>)}</ul></>}
          </section>}
          <details className="task-details__meta"><summary>{zh ? '任务配置与完成标准' : 'Task setup and completion criteria'}</summary><dl><dt>Agent</dt><dd>{details.agentName}<small>{details.effectiveAgentId}</small></dd><dt>{zh ? '输入' : 'Input'}</dt><dd>{details.input || '—'}</dd><dt>{zh ? '依赖' : 'Dependencies'}</dt><dd>{details.dependencies.length ? details.dependencies.join(' → ') : (zh ? '无' : 'None')}</dd><dt>{zh ? '尝试次数' : 'Attempt'}</dt><dd>{details.attempt}{details.maxAttempts ? ` / ${details.maxAttempts}` : ''}</dd><dt>{zh ? '完成标准' : 'Completion criteria'}</dt><dd>{details.completionCriteria.length ? <ul>{details.completionCriteria.map(item => <li key={item}>{item}</li>)}</ul> : '—'}</dd></dl></details>
          {!!details.evidence?.length && <section className="task-evidence"><strong>{zh ? '工具证据' : 'Tool evidence'} · {details.evidence.length}</strong>{details.evidence.map(item => <details key={item.call_id}><summary>{item.tool} · {item.call_id}</summary><small>{item.called_at}</small><pre>{item.arguments_excerpt}</pre><pre>{item.result_excerpt}</pre></details>)}</section>}
        </div>}
      </Drawer>
    </aside>
  )
}
