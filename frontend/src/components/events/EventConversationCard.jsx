import React from 'react'
import { Badge, Card, Collapse, Tag, Timeline, Typography } from 'antd'
import { BranchesOutlined, CheckCircleFilled, CloseCircleFilled, RobotOutlined, ToolOutlined } from '@ant-design/icons'
import { eventTimestamp, summarizeEvent } from '../../state/eventFeed'

const { Text } = Typography
export const EVENT_STATES = {
  completed: { color: '#16a34a', label: '已完成' }, failed: { color: '#dc2626', label: '失败' },
  working: { color: '#d97706', label: '执行中' }, submitted: { color: '#2563eb', label: '已提交' },
  'input-required': { color: '#7c3aed', label: '等待审批' }, canceled: { color: '#64748b', label: '已取消' },
}
const EVENT_LABELS = {
  'run.started': '运行开始', 'run.completed': '运行完成', 'run.failed': '运行失败', 'run.cancelled': '运行取消',
  'host.planning': 'Host 规划', 'host.plan_created': '计划已创建', 'host.plan_revised': '计划已调整', 'host.synthesis_started': '综合结果',
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
function eventIcon(event) {
  if (event.state === 'failed') return <CloseCircleFilled />
  if (event.event_type?.startsWith('tool.')) return <ToolOutlined />
  if (event.event_type === 'task.delegated') return <BranchesOutlined />
  return <CheckCircleFilled />
}
function EventEntry({ event }) {
  const detail = Object.keys(event.payload || {}).length ? event.payload : null
  return <div style={{ padding: '2px 0 12px' }}>
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
      <Tag variant="filled" color={event.conversation_type === 'multi' ? 'blue' : 'green'}>{event.conversation_type === 'multi' ? '多智能体' : '单智能体'}</Tag>
      <Text style={{ color: '#334155', fontWeight: 600 }}>{EVENT_LABELS[event.event_type] || event.event_type}</Text>
      <Text type="secondary" style={{ fontSize: 12 }}>{formatTime(eventTimestamp(event))}</Text>
    </div>
    <div style={{ color: '#475569', lineHeight: 1.65 }}>{summarizeEvent(event)}</div>
    {detail && <Collapse ghost size="small" items={[{ key: 'detail', label: <span style={{ fontSize: 12 }}>查看原始数据</span>, children: <pre className="event-payload-json">{JSON.stringify(detail, null, 2)}</pre> }]} />}
  </div>
}

export default function EventConversationCard({ conversationId, events, onSelect }) {
  const first = events[0]
  const state = EVENT_STATES[first.state] || { color: '#64748b', label: first.state || '未知' }
  return <Card key={conversationId} className="event-conversation-card" styles={{ body: { padding: '18px 22px 6px' } }}
    title={<div className="event-conversation-title"><Badge color={first.conversation_type === 'multi' ? '#2563eb' : '#16a34a'} /><span>{first.conversation_title || '未命名会话'}</span><Tag variant="filled">{first.conversation_type === 'multi' ? '多智能体' : '单智能体'}</Tag></div>}
    extra={<Text type="secondary">{events.length} 条事件</Text>}>
    <div className="event-conversation-meta"><span><RobotOutlined /> {first.agent_name || 'Host Agent'}</span><span>Task: <code>{first.task_id || '等待远程 Task ID'}</code></span><Tag variant="filled" style={{ color: state.color, background: `${state.color}12` }}>{state.label}</Tag></div>
    <Timeline items={events.map(event => ({ color: (EVENT_STATES[event.state] || {}).color || '#94a3b8', dot: eventIcon(event), children: <div className="event-timeline-entry" role="button" tabIndex={0} onClick={() => onSelect(event)} onKeyDown={keyEvent => { if (keyEvent.key === 'Enter') onSelect(event) }}><EventEntry event={event} /></div> }))} />
  </Card>
}
