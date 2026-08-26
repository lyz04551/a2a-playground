import React from 'react'
import { Button, Descriptions, Drawer, Empty, List, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { agentHealthView } from '../state/agentHealth'

const labels = { ready: ['就绪', 'Ready'], degraded: ['降级', 'Degraded'], offline: ['离线', 'Offline'], unknown: ['未知', 'Unknown'], ok: ['正常', 'OK'], error: ['异常', 'Error'] }
export default function AgentDetailDrawer({ agent, health, open, onClose, onTest, testing, zh }) {
  if (!agent) return null
  const view = agentHealthView(health); const tr = key => labels[key]?.[zh ? 0 : 1] || key
  return <Drawer title={zh ? 'Agent 详情' : 'Agent details'} open={open} onClose={onClose} width={620}>
    <div className="agent-detail-heading"><div><Typography.Title level={4}>{agent.name}</Typography.Title><Typography.Text type="secondary">{agent.url}</Typography.Text></div><Tag color={view.tone}>{tr(view.state)}</Tag></div>
    <Button icon={<ReloadOutlined />} loading={testing} onClick={onTest}>{zh ? '测试 Agent' : 'Test agent'}</Button>
    <Typography.Title level={5}>{zh ? '依赖状态' : 'Dependency status'}</Typography.Title>
    <Descriptions bordered size="small" column={1}>{Object.entries(health?.checks || {}).map(([name, check]) => <Descriptions.Item key={name} label={name.toUpperCase()}><Tag color={check.state === 'ok' ? 'success' : check.state === 'error' ? 'error' : 'default'}>{tr(check.state)}</Tag>{check.detail && <Typography.Text type="secondary">{check.detail}</Typography.Text>}</Descriptions.Item>)}<Descriptions.Item label={zh ? '延迟' : 'Latency'}>{health?.latency_ms == null ? '—' : `${health.latency_ms} ms`}</Descriptions.Item></Descriptions>
    <Typography.Title level={5}>{zh ? '能力与 Skills' : 'Capabilities and skills'}</Typography.Title>
    {agent.skills?.length ? <List size="small" bordered dataSource={agent.skills} renderItem={skill => <List.Item><List.Item.Meta title={skill.name || skill.id} description={skill.description} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    <Typography.Title level={5}>{zh ? 'Agent Card 原始信息' : 'Raw Agent Card'}</Typography.Title><pre className="agent-card-json">{JSON.stringify(agent, null, 2)}</pre>
  </Drawer>
}
