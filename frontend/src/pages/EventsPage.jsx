import React, { useState } from 'react'
import {
  Alert, Button, Card, Col, Empty, Input, Row, Segmented,
  Select, Spin, Statistic, Typography,
} from 'antd'
import {
  ApiOutlined, BranchesOutlined, CheckCircleFilled, CloseCircleFilled,
  FileTextOutlined, ReloadOutlined, RobotOutlined, SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import EventDetailDrawer from '../components/EventDetailDrawer'
import EventConversationCard from '../components/events/EventConversationCard'
import useEvents from '../hooks/useEvents'
import { useNavigate } from 'react-router-dom'

const { Text } = Typography

export default function EventsPage() {
  const navigate = useNavigate()
  const { loading, error, load, type, setType, state, setState, query, setQuery, view, setView, visibleEvents, groups, stats } = useEvents()
  const [selectedEvent, setSelectedEvent] = useState(null)

  return (
    <div className="events-page" style={{
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

        {error && <Alert type="error" showIcon message="事件加载失败" description={error} style={{ marginBottom: 18 }} />}

        <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
          {[
            ['事件总数', stats.total, <ApiOutlined />, '#0f172a'],
            ['已完成', stats.completed, <CheckCircleFilled />, '#16a34a'],
            ['失败', stats.failed, <CloseCircleFilled />, '#dc2626'],
            ['多智能体任务', stats.multi, <BranchesOutlined />, '#2563eb'],
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
            <Segmented value={view} onChange={setView} options={[{ label: '摘要', value: 'summary' }, { label: '完整事件', value: 'all' }, { label: '仅异常', value: 'errors' }, { label: '仅工具', value: 'tools' }]} />
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
        ) : groups.map(conversation => (
          <EventConversationCard key={conversation.id} conversation={conversation} view={view} onSelect={setSelectedEvent}
            onOpenWorkspace={run => navigate(`/workspace?mode=${run.mode}&conversation=${encodeURIComponent(conversation.id)}`)} />
        ))}
      </div>
      <EventDetailDrawer event={selectedEvent} open={Boolean(selectedEvent)} onClose={() => setSelectedEvent(null)} />
    </div>
  )
}
