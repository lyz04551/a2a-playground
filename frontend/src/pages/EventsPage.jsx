import React, { useEffect, useMemo, useState } from 'react'
import {
  Badge, Button, Card, Col, Collapse, Empty, Input, Row, Segmented,
  Select, Spin, Statistic, Tag, Timeline, Typography,
} from 'antd'
import {
  ApiOutlined, BranchesOutlined, CheckCircleFilled, CloseCircleFilled,
  FileTextOutlined, ReloadOutlined, RobotOutlined, SearchOutlined,
  ThunderboltOutlined, ToolOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'
import {
  eventTimestamp, filterEvents, groupEventsByConversation, summarizeEvent,
} from '../state/eventFeed'

const { Text } = Typography

const STATE = {
  completed: { color: '#16a34a', label: '已完成' },
  failed: { color: '#dc2626', label: '失败' },
  working: { color: '#d97706', label: '执行中' },
  submitted: { color: '#2563eb', label: '已提交' },
  'input-required': { color: '#7c3aed', label: '等待审批' },
  canceled: { color: '#64748b', label: '已取消' },
}

const EVENT_LABELS = {
  started: '任务开始',
  completed: '任务完成',
  routing: '智能体路由',
  tool_call: '工具调用',
  tool_result: '工具结果',
  status_update: '状态更新',
  error: '执行错误',
}

function formatTime(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function eventIcon(event) {
  if (event.state === 'failed') return <CloseCircleFilled />
  if (event.event_type?.startsWith('tool_')) return <ToolOutlined />
  if (event.event_type === 'routing') return <BranchesOutlined />
  return <CheckCircleFilled />
}

function EventDetail({ event }) {
  const detail = Object.keys(event.payload || {}).length ? event.payload : null
  return (
    <div style={{ padding: '2px 0 12px' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
        <Tag bordered={false} color={event.conversation_type === 'multi' ? 'blue' : 'green'}>
          {event.conversation_type === 'multi' ? '多智能体' : '单智能体'}
        </Tag>
        <Text style={{ color: '#334155', fontWeight: 600 }}>
          {EVENT_LABELS[event.event_type] || event.event_type}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>{formatTime(eventTimestamp(event))}</Text>
      </div>
      <div style={{ color: '#475569', lineHeight: 1.65 }}>{summarizeEvent(event)}</div>
      {detail && (
        <Collapse
          ghost
          size="small"
          items={[{
            key: 'detail',
            label: <span style={{ fontSize: 12, color: '#64748b' }}>查看原始数据</span>,
            children: (
              <pre style={{
                margin: 0, padding: 12, overflow: 'auto', borderRadius: 10,
                background: '#f8fafc', border: '1px solid #e2e8f0',
                color: '#334155', fontSize: 11, lineHeight: 1.55,
              }}>
                {JSON.stringify(detail, null, 2)}
              </pre>
            ),
          }]}
        />
      )}
    </div>
  )
}

export default function EventsPage() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [type, setType] = useState('all')
  const [state, setState] = useState('all')
  const [query, setQuery] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setEvents(await api.listEvents())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const visibleEvents = useMemo(
    () => filterEvents(events, { type, state, query }),
    [events, type, state, query],
  )
  const grouped = useMemo(() => groupEventsByConversation(visibleEvents), [visibleEvents])
  const groups = Object.entries(grouped)
  const completed = events.filter(event => event.state === 'completed').length
  const failed = events.filter(event => event.state === 'failed').length
  const multi = new Set(events.filter(event => event.conversation_type === 'multi').map(event => event.conversation_id)).size

  return (
    <div style={{
      minHeight: '100vh', overflow: 'auto', padding: '30px clamp(20px, 4vw, 54px) 56px',
      background: 'radial-gradient(circle at 90% 0%, #dbeafe 0, transparent 26%), #f8fafc',
    }}>
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 38, height: 38, display: 'grid', placeItems: 'center', borderRadius: 12,
                color: '#fff', background: '#0f172a', boxShadow: '0 8px 20px rgba(15,23,42,.16)',
              }}>
                <ThunderboltOutlined />
              </div>
              <h1 style={{ margin: 0, color: '#0f172a', fontSize: 27, letterSpacing: '-.03em' }}>执行事件</h1>
            </div>
            <p style={{ margin: '9px 0 0 48px', color: '#64748b' }}>
              汇总单智能体对话与多智能体任务的完整执行轨迹
            </p>
          </div>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        </div>

        <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
          {[
            ['事件总数', events.length, <ApiOutlined />, '#0f172a'],
            ['已完成', completed, <CheckCircleFilled />, '#16a34a'],
            ['失败', failed, <CloseCircleFilled />, '#dc2626'],
            ['多智能体任务', multi, <BranchesOutlined />, '#2563eb'],
          ].map(([label, value, icon, color]) => (
            <Col xs={12} lg={6} key={label}>
              <Card styles={{ body: { padding: '17px 19px' } }} style={{ borderRadius: 14, borderColor: '#e2e8f0' }}>
                <Statistic title={label} value={value} prefix={React.cloneElement(icon, { style: { color } })}
                  valueStyle={{ color: '#0f172a', fontSize: 23, fontWeight: 700 }} />
              </Card>
            </Col>
          ))}
        </Row>

        <Card style={{ borderRadius: 16, borderColor: '#e2e8f0', marginBottom: 18 }}
          styles={{ body: { padding: 16 } }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <Segmented
              value={type}
              onChange={setType}
              options={[
                { label: '全部', value: 'all' },
                { label: '单智能体', value: 'single', icon: <RobotOutlined /> },
                { label: '多智能体', value: 'multi', icon: <BranchesOutlined /> },
              ]}
            />
            <Select
              value={state}
              onChange={setState}
              style={{ width: 132 }}
              options={[
                { value: 'all', label: '全部状态' },
                { value: 'completed', label: '已完成' },
                { value: 'working', label: '执行中' },
                { value: 'failed', label: '失败' },
                { value: 'input-required', label: '等待审批' },
              ]}
            />
            <Input
              allowClear value={query} onChange={event => setQuery(event.target.value)}
              prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
              placeholder="搜索会话、Agent、Task 或工具"
              style={{ flex: '1 1 280px', maxWidth: 460 }}
            />
            <Text type="secondary" style={{ marginLeft: 'auto' }}>显示 {visibleEvents.length} 条</Text>
          </div>
        </Card>

        {loading ? (
          <div style={{ height: 320, display: 'grid', placeItems: 'center' }}><Spin size="large" /></div>
        ) : groups.length === 0 ? (
          <Card style={{ borderRadius: 16, borderColor: '#e2e8f0' }}>
            <Empty image={<FileTextOutlined style={{ fontSize: 52, color: '#cbd5e1' }} />}
              description="暂无符合条件的事件" />
          </Card>
        ) : groups.map(([conversationId, items]) => {
          const first = items[0]
          const stateInfo = STATE[first.state] || { color: '#64748b', label: first.state || '未知' }
          return (
            <Card
              key={conversationId}
              style={{ marginBottom: 14, borderRadius: 16, borderColor: '#e2e8f0', overflow: 'hidden' }}
              styles={{ body: { padding: '18px 22px 6px' } }}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                  <Badge color={first.conversation_type === 'multi' ? '#2563eb' : '#16a34a'} />
                  <span style={{ color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {first.conversation_title || '未命名会话'}
                  </span>
                  <Tag bordered={false}>{first.conversation_type === 'multi' ? '多智能体' : '单智能体'}</Tag>
                </div>
              }
              extra={<Text type="secondary">{items.length} 条事件</Text>}
            >
              <div style={{
                display: 'flex', gap: 16, flexWrap: 'wrap', paddingBottom: 17, marginBottom: 16,
                borderBottom: '1px solid #f1f5f9', fontSize: 12, color: '#64748b',
              }}>
                <span><RobotOutlined /> {first.agent_name || 'Host Agent'}</span>
                <span>Task: <code>{first.task_id || '等待远程 Task ID'}</code></span>
                <Tag bordered={false} style={{ color: stateInfo.color, background: `${stateInfo.color}12` }}>
                  {stateInfo.label}
                </Tag>
              </div>
              <Timeline
                items={items.map(event => ({
                  color: (STATE[event.state] || {}).color || '#94a3b8',
                  dot: eventIcon(event),
                  children: <EventDetail event={event} />,
                }))}
              />
            </Card>
          )
        })}
      </div>
    </div>
  )
}
