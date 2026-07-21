import React, { useState, useEffect, useMemo } from 'react'
import { Card, Tag, Spin, Empty, Typography, Timeline, Badge, Row, Col, Statistic } from 'antd'
import {
  FileTextOutlined, CheckCircleOutlined, CloseCircleOutlined,
  SyncOutlined, ClockCircleOutlined, ThunderboltOutlined,
  BranchesOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'

const { Text } = Typography

const STATE_COLORS = {
  completed: 'green',
  failed: 'red',
  working: 'orange',
  submitted: 'blue',
  canceled: 'default',
  'input-required': 'purple',
}

const STATE_ICONS = {
  completed: <CheckCircleOutlined />,
  failed: <CloseCircleOutlined />,
  working: <SyncOutlined spin />,
  submitted: <ClockCircleOutlined />,
  canceled: <CloseCircleOutlined />,
}

export default function EventsPage() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const [agents, convs, allEvents] = await Promise.all([
          api.listAgents(),
          api.listConversations(''),
          api.listEvents(),
        ])
        const agentIds = new Set(agents.map(a => a.id))
        const activeConvIds = new Set(
          convs.filter(c => agentIds.has(c.agent_id)).map(c => c.id)
        )
        setEvents(allEvents.filter(e => activeConvIds.has(e.conversation_id)))
      } catch { /* ignore */ }
      setLoading(false)
    })()
  }, [])

  const grouped = useMemo(() => {
    const map = {}
    for (const e of events) {
      const key = e.conversation_id || 'unknown'
      if (!map[key]) map[key] = []
      map[key].push(e)
    }
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''))
    }
    return map
  }, [events])

  const convIds = Object.keys(grouped)

  // Stats
  const completedCount = events.filter(e => e.state === 'completed').length
  const failedCount = events.filter(e => e.state === 'failed').length
  const workingCount = events.filter(e => e.state === 'working').length

  return (
    <div style={{ padding: 32, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: '#1e293b' }}>Task Events</h2>
        <p style={{ margin: '6px 0 0', color: '#94a3b8', fontSize: 14 }}>
          Real-time event stream from agent conversations
        </p>
      </div>

      {/* Stats */}
      {events.length > 0 && (
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Total Events</span>}
                value={events.length}
                prefix={<ThunderboltOutlined style={{ color: '#10b981', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Completed</span>}
                value={completedCount}
                prefix={<CheckCircleOutlined style={{ color: '#10b981', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#10b981' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Failed</span>}
                value={failedCount}
                prefix={<CloseCircleOutlined style={{ color: '#ef4444', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#ef4444' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Conversations</span>}
                value={convIds.length}
                prefix={<BranchesOutlined style={{ color: '#6366f1', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {loading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin size="large" />
        </div>
      ) : convIds.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty
            image={<FileTextOutlined style={{ fontSize: 56, color: '#d9d9d9' }} />}
            description={
              <span style={{ color: '#94a3b8', fontSize: 14 }}>
                No events yet — they appear when you chat with agents
              </span>
            }
          />
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', paddingBottom: 16 }}>
          {convIds.map((convId) => (
            <Card
              key={convId}
              size="small"
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <BranchesOutlined style={{ color: '#10b981' }} />
                  <span style={{ fontSize: 13, fontFamily: "'JetBrains Mono', monospace", color: '#64748b' }}>
                    {convId.slice(0, 8)}...{convId.slice(-6)}
                  </span>
                </div>
              }
              extra={
                <Tag style={{ borderRadius: 10, fontSize: 11 }}>
                  {grouped[convId].length} events
                </Tag>
              }
              style={{
                marginBottom: 16, borderRadius: 12,
                border: '1px solid #f0f0f0',
                boxShadow: '0 1px 4px rgba(0,0,0,0.02)',
              }}
              styles={{ body: { padding: '16px 20px' } }}
            >
              <Timeline
                items={grouped[convId].map((e, i) => ({
                  color: STATE_COLORS[e.state] || 'gray',
                  dot: STATE_ICONS[e.state] || null,
                  children: (
                    <div key={e.id} style={{ animation: `fadeIn 0.3s ease-out ${i * 30}ms` }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Tag
                          color={STATE_COLORS[e.state] || 'default'}
                          style={{ fontSize: 10, margin: 0, borderRadius: 4, lineHeight: '18px' }}
                        >
                          {e.state}
                        </Tag>
                        <Text
                          type="secondary"
                          style={{
                            fontSize: 11,
                            fontFamily: "'JetBrains Mono', monospace",
                            color: '#94a3b8',
                          }}
                        >
                          {e.event_type}
                        </Text>
                        <Text
                          type="secondary"
                          style={{
                            fontSize: 11,
                            marginLeft: 'auto',
                            fontFamily: "'JetBrains Mono', monospace",
                            color: '#cbd5e1',
                          }}
                        >
                          {new Date(e.timestamp).toLocaleTimeString()}
                        </Text>
                      </div>
                      <Text
                        style={{
                          fontSize: 13, color: '#64748b', display: 'block',
                          lineHeight: 1.5,
                        }}
                        ellipsis={{ rows: 2 }}
                      >
                        {e.content || '—'}
                      </Text>
                    </div>
                  ),
                }))}
              />
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
