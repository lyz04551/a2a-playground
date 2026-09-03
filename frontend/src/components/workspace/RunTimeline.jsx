import React from 'react'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  CodeOutlined,
  LoadingOutlined,
  NodeIndexOutlined,
  PauseCircleOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import { buildToolDetails, groupToolCalls, statusLabel } from './taskDetails'
import { buildRoundTimeline, roundDisplayText } from './roundTimeline'
import { formatAgentOutput } from './agentOutput'
import ApprovalCard from '../ApprovalCard'

function StatusIcon({ status }) {
  if (status === 'completed') return <CheckCircleFilled />
  if (status === 'failed') return <CloseCircleFilled />
  if (status === 'waiting' || status === 'approval_required') return <PauseCircleOutlined />
  return <LoadingOutlined spin={status === 'working' || status === 'delegated'} />
}

function formatDuration(durationMs) {
  if (!Number.isFinite(durationMs)) return '—'
  if (durationMs < 1000) return `${durationMs} ms`
  return `${(durationMs / 1000).toFixed(durationMs < 10000 ? 1 : 0)} s`
}

async function copyText(value) {
  if (value && navigator?.clipboard) await navigator.clipboard.writeText(value)
}

function ToolCallDetail({ tool, zh }) {
  const details = buildToolDetails(tool)
  return (
    <details className={`tool-call-detail status-${tool.status || 'working'}`}>
      <summary>
        <span><StatusIcon status={tool.status} /> {tool.name || (zh ? '工具调用' : 'Tool call')}</span>
        <small><StatusIcon status={tool.status} /> {statusLabel(tool.status || 'working', zh)} · {formatDuration(tool.durationMs)}</small>
      </summary>
      {tool.error && <code>{details.errorText}</code>}
      <section>
        <header><span>{zh ? '调用参数' : 'Arguments'}</span>{details.argumentsText && <button type="button" onClick={() => copyText(details.argumentsText)}>{zh ? '复制' : 'Copy'}</button>}</header>
        <pre>{details.argumentsText || '—'}</pre>
      </section>
      <section>
        <header><span>{zh ? '返回内容' : 'Result'}</span>{details.resultText && <button type="button" onClick={() => copyText(details.resultText)}>{zh ? '复制' : 'Copy'}</button>}</header>
        <pre>{details.resultText || (tool.status === 'working' ? (zh ? '等待工具返回…' : 'Awaiting tool result…') : '—')}</pre>
      </section>
    </details>
  )
}

function ToolActivity({ tools, zh }) {
  const groups = groupToolCalls(tools)
  const completed = tools.filter(tool => tool.status === 'completed').length
  const failed = tools.filter(tool => tool.status === 'failed').length
  const active = tools.filter(tool => !['completed', 'failed'].includes(tool.status))
  const percent = tools.length ? Math.round((completed + failed) / tools.length * 100) : 0
  return (
    <li className="run-timeline__node is-tool-summary">
      <span className="run-timeline__rail"><CodeOutlined /></span>
      <details className="tool-activity">
        <summary>
          <span className="tool-activity__title"><strong>{zh ? '工具活动' : 'Tool activity'}</strong><small>{completed}/{tools.length} {zh ? '已完成' : 'completed'}{failed ? ` · ${failed} ${zh ? '失败' : 'failed'}` : ''}</small></span>
          <span className="tool-activity__count">{groups.length} {zh ? '类' : 'types'} · {tools.length} {zh ? '次' : 'calls'}</span>
        </summary>
        <div className="tool-activity__progress" aria-label={`${percent}%`}><i style={{ width: `${percent}%` }} /></div>
        {active.length > 0 && <div className="tool-activity__active"><span>{zh ? '正在执行' : 'Active'}</span>{[...new Set(active.map(tool => tool.name))].slice(0, 3).map(name => <code key={name}>{name}</code>)}</div>}
        <div className="tool-groups">
          {groups.map(group => (
            <details className="tool-group" key={group.name}>
              <summary><span>{group.name}</span><small>× {group.total} · {group.completed} ✓{group.working ? ` · ${group.working} …` : ''}{group.failed ? ` · ${group.failed} !` : ''}</small></summary>
              <div className="tool-group__calls">{group.items.map(tool => <ToolCallDetail tool={tool} zh={zh} key={tool.id} />)}</div>
            </details>
          ))}
        </div>
      </details>
    </li>
  )
}

export default function RunTimeline({ run = {}, tasks = [], rounds = [], approvals = [], onApproval, onTaskSelect, selectedTaskId, language = 'en-US' }) {
  const zh = language.startsWith('zh')
  const visibleTasks = tasks.filter(task => (
    task.agentId || task.agentName || task.objective
  ))
  const timelineItems = buildRoundTimeline(visibleTasks, rounds)
  return (
    <ol className="run-timeline" aria-label="Host to Agent execution timeline">
      <li className="run-timeline__node is-host">
        <span className="run-timeline__rail"><NodeIndexOutlined /></span>
        <div><strong>Host Agent</strong><small>{statusLabel(run.status || 'idle', zh)}</small></div>
      </li>
      {timelineItems.map(item => item.kind === 'decision' ? (
        <li className={`run-timeline__node is-decision status-${item.round.status || 'working'}`} key={item.id}>
          <span className="run-timeline__rail"><NodeIndexOutlined /></span>
          <section><strong>{zh ? `Host 第 ${item.round.round} 轮决策` : `Host decision round ${item.round.round}`}</strong><span>{roundDisplayText(item.round, zh)}</span><small>{statusLabel(item.round.status || item.round.action, zh)}</small></section>
        </li>
      ) : (
        <React.Fragment key={item.id}>
          <li className={`run-timeline__node is-agent status-${item.task.status || 'queued'}`}>
            <span className="run-timeline__rail"><RobotOutlined /></span>
            <button type="button" className={`run-timeline__task${selectedTaskId === item.task.id ? ' is-selected' : ''}`} onClick={() => onTaskSelect?.(item.task)} aria-label={`Open details for ${item.task.objective || item.task.label || item.task.id}`}><strong>{item.task.agentName || item.task.agentId || 'Agent task'}</strong><span>{item.task.objective || item.task.label || item.task.id}</span><small><StatusIcon status={item.task.status} /> {statusLabel(item.task.status || 'queued', zh)} · {formatDuration(item.task.durationMs)}</small>{(item.task.output || item.task.streamingOutput || item.task.result) && <pre className="run-timeline__agent-output">{formatAgentOutput(item.task.output || item.task.streamingOutput || item.task.result)}</pre>}{item.task.error && <code>{typeof item.task.error === 'string' ? item.task.error : item.task.error.message || JSON.stringify(item.task.error)}</code>}</button>
          </li>
          {(item.task.tools || []).length > 0 && <ToolActivity tools={item.task.tools} zh={zh} />}
          {approvals.filter(approval => (approval.taskId || approval.task_id) === item.task.id).map(approval => (
            <li className="run-timeline__node is-approval" key={approval.id}>
              <ApprovalCard approval={approval} previousApproval={approval.previousApproval} language={language} onDecide={onApproval} />
            </li>
          ))}
        </React.Fragment>
      ))}
      {run.hostSummary && <li className="run-timeline__node is-host-summary"><span className="run-timeline__rail"><NodeIndexOutlined /></span><section><strong>{zh ? 'Host 最终总结' : 'Host final summary'}</strong><pre>{formatAgentOutput(run.hostSummary)}</pre></section></li>}
    </ol>
  )
}
