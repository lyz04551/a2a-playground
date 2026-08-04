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

export default function RunTimeline({ run = {}, tasks = [] }) {
  return (
    <ol className="run-timeline" aria-label="Host to Agent execution timeline">
      <li className="run-timeline__node is-host">
        <span className="run-timeline__rail"><NodeIndexOutlined /></span>
        <div><strong>Host Agent</strong><small>{run.status || 'idle'}</small></div>
      </li>
      {tasks.map(task => (
        <React.Fragment key={task.id}>
          <li className={`run-timeline__node is-agent status-${task.status || 'queued'}`}>
            <span className="run-timeline__rail"><RobotOutlined /></span>
            <div><strong>{task.label || task.agentName || task.agentId || 'Agent task'}</strong><small><StatusIcon status={task.status} /> {task.status || 'queued'} · {formatDuration(task.durationMs)}</small>{task.error && <code>{typeof task.error === 'string' ? task.error : task.error.message || JSON.stringify(task.error)}</code>}</div>
          </li>
          {(task.tools || []).map(tool => (
            <li className={`run-timeline__node is-tool status-${tool.status || 'working'}`} key={tool.id}>
              <span className="run-timeline__rail"><CodeOutlined /></span>
              <div><strong>{tool.name || 'Tool call'}</strong><small><StatusIcon status={tool.status} /> {tool.status || 'working'}</small>{tool.result !== undefined && <details><summary>Result</summary><pre>{typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)}</pre></details>}</div>
            </li>
          ))}
        </React.Fragment>
      ))}
    </ol>
  )
}
