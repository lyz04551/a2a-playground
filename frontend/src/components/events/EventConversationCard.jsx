import React from 'react'
import { Badge, Button, Card, Collapse, Tag, Timeline, Typography } from 'antd'
import { BranchesOutlined, CheckCircleFilled, ClockCircleOutlined, CloseCircleFilled, ExportOutlined, RobotOutlined, ToolOutlined } from '@ant-design/icons'
import { buildToolDetails } from '../workspace/taskDetails'
import { eventTimestamp, filterEventsByView, summarizeEvent } from '../../state/eventFeed'

const { Text } = Typography
export const EVENT_STATES = {
  completed: { color: '#16a34a', label: '已完成' }, failed: { color: '#dc2626', label: '失败' },
  working: { color: '#d97706', label: '执行中' }, submitted: { color: '#2563eb', label: '已提交' },
  'input-required': { color: '#7c3aed', label: '等待审批' }, canceled: { color: '#64748b', label: '已取消' },
}
const EVENT_LABELS = {
  'run.started': '运行开始', 'run.completed': '运行完成', 'run.failed': '运行失败', 'run.cancelled': '运行取消',
  'host.planning': 'Host 规划', 'host.plan_created': '计划已创建', 'host.plan_revised': '计划已调整', 'host.synthesis_started': 'Host 综合',
  'task.context_prepared': '准备任务上下文', 'task.delegated': '分派任务', 'task.started': '任务开始', 'task.retry_scheduled': '任务重试',
  'task.evaluated': '结果评价', 'task.completed': '任务完成', 'task.failed': '任务失败', 'task.blocked': '任务阻塞',
  'message.delta': '回复生成中', 'message.completed': '最终回复', 'tool.called': '工具调用', 'tool.completed': '工具完成',
  'approval.required': '等待审批', 'approval.decided': '审批完成',
}

function formatTime(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function shortId(value) {
  if (!value) return '—'
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value
}

function eventIcon(event) {
  if (event.state === 'failed') return <CloseCircleFilled />
  if (event.event_type?.startsWith('tool.')) return <ToolOutlined />
  if (event.event_type === 'task.delegated') return <BranchesOutlined />
  return <CheckCircleFilled />
}

function EventEntry({ event, onSelect }) {
  return <div className="event-timeline-entry" role="button" tabIndex={0} onClick={() => onSelect(event)} onKeyDown={keyEvent => { if (keyEvent.key === 'Enter') onSelect(event) }}>
    <div className="event-entry-heading"><Text strong>{EVENT_LABELS[event.event_type] || event.event_type}</Text><Text type="secondary">{formatTime(eventTimestamp(event))}</Text></div>
    <div className="event-entry-summary">{summarizeEvent(event)}</div>
  </div>
}

function ToolCall({ tool }) {
  const detail = buildToolDetails(tool)
  const state = EVENT_STATES[tool.status] || EVENT_STATES.working
  const panels = [
    detail.argumentsText && { key: 'arguments', label: '调用参数', children: <pre className="event-payload-json">{detail.argumentsText}</pre> },
    detail.resultText && { key: 'result', label: '返回内容', children: <pre className="event-payload-json">{detail.resultText}</pre> },
    detail.errorText && { key: 'error', label: '错误信息', children: <pre className="event-payload-json">{detail.errorText}</pre> },
  ].filter(Boolean)
  return <div className="event-tool-call">
    <div className="event-tool-call__head"><span><ToolOutlined /> <strong>{tool.name}</strong></span><span className="event-tool-call__meta"><Badge color={state.color} text={state.label} />{tool.durationMs != null && <Text type="secondary">{tool.durationMs} ms</Text>}</span></div>
    <div className="event-id-row"><span>Call ID</span><code title={tool.id}>{shortId(tool.id)}</code></div>
    {panels.length > 0 && <Collapse ghost size="small" items={panels} />}
  </div>
}

function TaskCard({ task, mode }) {
  const state = EVENT_STATES[task.status] || EVENT_STATES.submitted
  return <div className={`event-task-card${task.parentTaskId ? ' event-task-card--child' : ''}`}>
    <div className="event-task-card__head"><div className="event-task-icon"><RobotOutlined /></div><div className="event-task-title"><strong>{task.agentName}</strong><span>{mode === 'direct' ? '目标 Agent A2A Task' : task.parentTaskId ? 'Agent A2A 子任务' : 'Host Root Task'}</span></div><Tag bordered={false} color={state.color}>{state.label}</Tag></div>
    <div className="event-task-ids">
      <div className="event-id-row"><span>Local Task</span><code title={task.id}>{shortId(task.id)}</code></div>
      <div className="event-id-row"><span>Remote A2A Task</span><code title={task.remoteTaskId}>{shortId(task.remoteTaskId)}</code></div>
      {task.parentTaskId && <div className="event-id-row"><span>Parent</span><code title={task.parentTaskId}>{shortId(task.parentTaskId)}</code></div>}
    </div>
    {task.tools.length > 0 && <div className="event-tools-block"><div className="event-section-label"><ToolOutlined /> 工具活动 <Tag>{task.tools.length}</Tag></div>{task.tools.map(tool => <ToolCall key={tool.id} tool={tool} />)}</div>}
  </div>
}

function RunCard({ run, view, onSelect, onOpenWorkspace }) {
  const state = EVENT_STATES[run.status] || EVENT_STATES.submitted
  const timelineEvents = filterEventsByView(run.events, view)
  const tasks = view === 'tools' ? run.tasks.filter(task => task.tools.length > 0) : run.tasks
  const hostMilestones = run.milestones.filter(event => ['host.plan_created', 'host.synthesis_started', 'message.completed'].includes(event.event_type))
  return <section className="event-run-card">
    <header className="event-run-header"><div><div className="event-run-title"><Tag className={`event-mode-tag event-mode-tag--${run.mode}`}>{run.mode.toUpperCase()}</Tag><strong>{run.mode === 'auto' ? 'Host 编排运行' : `${run.targetAgentName || '目标 Agent'} 直连运行`}</strong><Badge color={state.color} text={state.label} /></div><div className="event-run-meta"><code title={run.id}>{shortId(run.id)}</code><span><ClockCircleOutlined /> {formatTime(run.startedAt)}</span><span>{run.events.length} 条事件</span></div></div><Button size="small" icon={<ExportOutlined />} onClick={() => onOpenWorkspace(run)}>在工作台打开</Button></header>
    {run.mode === 'auto' && hostMilestones.length > 0 && <div className="event-host-strip">{hostMilestones.map(event => <span key={event.id}><CheckCircleFilled /> {EVENT_LABELS[event.event_type]}</span>)}</div>}
    {tasks.length > 0 && <div className="event-task-list">{tasks.map(task => <TaskCard key={task.id} task={task} mode={run.mode} />)}</div>}
    {timelineEvents.length > 0 && <Collapse className="event-raw-events" ghost items={[{ key: 'events', label: `${view === 'all' ? '完整' : view === 'errors' ? '异常' : view === 'tools' ? '工具原始' : '关键'}事件 (${timelineEvents.length})`, children: <Timeline items={timelineEvents.map(event => ({ color: (EVENT_STATES[event.state] || {}).color || '#94a3b8', dot: eventIcon(event), children: <EventEntry event={event} onSelect={onSelect} /> }))} /> }]} />}
  </section>
}

export default function EventConversationCard({ conversation, view, onSelect, onOpenWorkspace }) {
  return <Card className="event-conversation-card" styles={{ body: { padding: '0' } }} title={<div className="event-conversation-title"><Badge color={conversation.type === 'multi' ? '#2563eb' : '#16a34a'} /><span>{conversation.title}</span><Tag bordered={false}>{conversation.type === 'multi' ? '多智能体' : '单智能体'}</Tag></div>} extra={<Text type="secondary">{conversation.runs.length} 次运行 · {conversation.events.length} 条事件</Text>}>
    <div className="event-run-list">{conversation.runs.map(run => <RunCard key={run.id} run={run} view={view} onSelect={onSelect} onOpenWorkspace={onOpenWorkspace} />)}</div>
  </Card>
}
