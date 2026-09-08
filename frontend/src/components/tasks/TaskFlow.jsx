import React from 'react'
import { CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, FileTextOutlined, MessageOutlined, RobotOutlined, SafetyCertificateOutlined, ToolOutlined } from '@ant-design/icons'

const icons = { host: <RobotOutlined />, round: <ClockCircleOutlined />, agent: <RobotOutlined />, tool: <ToolOutlined />, approval: <SafetyCertificateOutlined />, result: <MessageOutlined />, summary: <FileTextOutlined /> }
const stateIcon = status => ['failed', 'blocked', 'rejected'].includes(status) ? <ExclamationCircleOutlined /> : status === 'completed' || status === 'approved' ? <CheckCircleOutlined /> : <ClockCircleOutlined />

export default function TaskFlow({ nodes, selectedId, onSelect, zh }) {
  if (!nodes.length) return <div className="task-explorer__empty">{zh ? '这个 Run 暂无任务事件' : 'No task events for this run'}</div>
  return <ol className="task-flow">{nodes.map(node => <li key={node.id} className={`task-flow__node is-${node.kind}`} style={{ '--task-depth': node.depth }}><button type="button" className={selectedId === node.id ? 'is-selected' : ''} onClick={() => onSelect(node)}><span className="task-flow__icon">{icons[node.kind]}</span><span className="task-flow__copy"><strong>{node.title}</strong>{node.subtitle && <small>{String(node.subtitle).slice(0, 220)}</small>}</span><span className={`task-flow__status is-${node.status}`}>{stateIcon(node.status)} {node.status}</span></button></li>)}</ol>
}
