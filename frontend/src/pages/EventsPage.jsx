import React, { useState, useEffect, useMemo } from 'react'
import { Card, Tag, Spin, Empty, Typography } from 'antd'
import { FileTextOutlined } from '@ant-design/icons'
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

  return (
    <div style={{ padding: 32, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Task Events</h2>
        <p style={{ margin: '4px 0 0', color: '#9ca3af', fontSize: 14 }}>
          {events.length > 0
            ? `${events.length} events across ${convIds.length} conversation${convIds.length > 1 ? 's' : ''}`
            : 'No events recorded'}
        </p>
      </div>

      {loading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin size="large" />
        </div>
      ) : convIds.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty
            image={<FileTextOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
            description="No events yet — they appear when you chat with agents"
          />
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', paddingBottom: 16 }}>
          {convIds.map((convId) => (
            <Card
              key={convId}
              size="small"
              title={
                <span style={{ fontSize: 13, fontFamily: 'monospace', color: '#6b7280' }}>
                  Conversation: {convId.slice(0, 20)}...
                </span>
              }
              extra={<Tag>{grouped[convId].length} events</Tag>}
              style={{ marginBottom: 12 }}
            >
              {grouped[convId].map((e, i) => (
                <div
                  key={e.id}
                  style={{
                    padding: '8px 0',
                    borderBottom: i < grouped[convId].length - 1 ? '1px solid #f0f0f0' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Tag color={STATE_COLORS[e.state] || 'default'} style={{ fontSize: 10, margin: 0 }}>
                      {e.state}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>{e.event_type}</Text>
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto', fontFamily: 'monospace' }}>
                      {new Date(e.timestamp).toLocaleTimeString()}
                    </Text>
                  </div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block' }} ellipsis={{ rows: 2 }}>
                    {e.content || '—'}
                  </Text>
                </div>
              ))}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
