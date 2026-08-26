import React from 'react'
import { Button, Card, Popconfirm, Tag, Tooltip } from 'antd'
import { DeleteOutlined, MessageOutlined, TagsOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { agentHealthView } from '../../state/agentHealth'

const statusText = (state, zh) => ({ ready: zh ? '就绪' : 'Ready', degraded: zh ? '降级' : 'Degraded', offline: zh ? '离线' : 'Offline', unknown: zh ? '未知' : 'Unknown' })[state]

export default function AgentCard({ agent, health, index, zh, onOpen, onChat, onDelete }) {
  const healthView = agentHealthView(health)
  const status = statusText(healthView.state, zh)
  return <Card size="small" hoverable className="agent-card" onClick={onOpen}
    style={{ animationDelay: `${index * 50}ms` }} styles={{ body: { padding: 0, flex: 1 } }}
    actions={[
      <Tooltip title={zh ? '与该 Agent 对话' : 'Chat with this agent'} key="chat"><Button type="text" icon={<MessageOutlined />} onClick={event => { event.stopPropagation(); onChat() }}>{zh ? '对话' : 'Chat'}</Button></Tooltip>,
      <Popconfirm key="delete" title={zh ? '删除智能体？' : 'Delete agent?'} description={zh ? `确定移除“${agent.name}”？` : `Remove "${agent.name}"?`} onConfirm={onDelete} okText={zh ? '删除' : 'Delete'} cancelText={zh ? '取消' : 'Cancel'} okButtonProps={{ danger: true }}><Button type="text" danger icon={<DeleteOutlined />} onClick={event => event.stopPropagation()}>{zh ? '移除' : 'Remove'}</Button></Popconfirm>,
    ]}>
    <div className="agent-card-accent" />
    <div className="agent-card-body">
      <div className="agent-card-header">
        <div className="agent-avatar">{agent.name?.charAt(0)?.toUpperCase() || 'A'}</div>
        <div className="agent-identity"><strong>{agent.name}</strong><code>{agent.url?.replace(/^https?:\/\//, '')}</code></div>
        <Tooltip title={`${status}${health?.latency_ms == null ? '' : ` · ${health.latency_ms}ms`}`}><span className={`agent-health agent-health--${healthView.state}`}><i />{status}</span></Tooltip>
        <Tooltip title={agent.capabilities?.streaming ? (zh ? '支持流式响应' : 'Streaming enabled') : (zh ? '标准响应' : 'Standard mode')}><span className={`agent-streaming ${agent.capabilities?.streaming ? 'is-enabled' : ''}`}><ThunderboltOutlined /></span></Tooltip>
      </div>
      <div className="agent-tags">{agent.version && <Tag>v{agent.version}</Tag>}{agent.preferredTransport && <Tag>{agent.preferredTransport}</Tag>}{agent.protocolVersion && <Tag>{agent.protocolVersion}</Tag>}</div>
      {agent.description && <p className="agent-description">{agent.description}</p>}
      {agent.skills?.length > 0 && <div className="agent-skills"><div><TagsOutlined /> Skills</div><div>{agent.skills.map(skill => <Tag key={skill.id || skill.name}>{skill.name || skill.id}</Tag>)}</div></div>}
    </div>
  </Card>
}
