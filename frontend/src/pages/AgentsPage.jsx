import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Button, Modal, Input, Tag, Spin, Empty, Pagination, message, Tooltip, Popconfirm, Statistic, Row, Col, Badge
} from 'antd'
import {
  PlusOutlined, MessageOutlined, DeleteOutlined, SearchOutlined,
  RobotOutlined, ApiOutlined, ThunderboltOutlined, TagsOutlined,
  CheckCircleOutlined, CloseCircleOutlined, AimOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'

export default function AgentsPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const pageSize = 9

  const filteredAgents = searchQuery
    ? agents.filter(a => {
        const q = searchQuery.toLowerCase()
        return (a.name || '').toLowerCase().includes(q)
          || (a.description || '').toLowerCase().includes(q)
          || (a.skills || []).some(s =>
              (s.name || s.id || '').toLowerCase().includes(q)
              || (s.tags || []).some(t => t.toLowerCase().includes(q))
            )
      })
    : agents

  const totalPages = Math.ceil(filteredAgents.length / pageSize) || 1
  const paginatedAgents = filteredAgents.slice((page - 1) * pageSize, page * pageSize)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const list = await api.listAgents()
      setAgents(list)
      setPage(1)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleDelete = async (agent) => {
    try {
      await api.deleteAgent(agent.id)
      message.success(`Removed ${agent.name}`)
      await load()
    } catch { message.error('Failed to delete agent') }
  }

  // Stats
  const streamingCount = agents.filter(a => a.capabilities?.streaming).length
  const totalSkills = agents.reduce((sum, a) => sum + (a.skills?.length || 0), 0)

  return (
    <div style={{ padding: 32, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 24,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: '#1e293b' }}>Agents</h2>
          <p style={{ margin: '6px 0 0', color: '#94a3b8', fontSize: 14 }}>
            Manage and monitor your A2A agents
          </p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setShowModal(true)}
          size="large"
          style={{ height: 42, paddingInline: 24, fontWeight: 600, borderRadius: 10 }}
        >
          Add Agent
        </Button>
      </div>

      {/* Stats Overview */}
      {agents.length > 0 && (
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Total Agents</span>}
                value={agents.length}
                prefix={<RobotOutlined style={{ color: '#10b981', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Streaming</span>}
                value={streamingCount}
                suffix={<span style={{ fontSize: 12, color: '#94a3b8' }}>/ {agents.length}</span>}
                prefix={<ThunderboltOutlined style={{ color: '#f59e0b', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Total Skills</span>}
                value={totalSkills}
                prefix={<TagsOutlined style={{ color: '#6366f1', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" style={{ borderRadius: 10, border: '1px solid #f0f0f0' }} hoverable>
              <Statistic
                title={<span style={{ fontSize: 12, color: '#94a3b8' }}>Protocol</span>}
                value="A2A"
                prefix={<ApiOutlined style={{ color: '#06b5ce', fontSize: 18 }} />}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* Search */}
      {agents.length > 0 && (
        <Input.Search
          placeholder="Search agents by name, description, or skills..."
          allowClear
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1) }}
          onSearch={() => {}}
          style={{ marginBottom: 20 }}
          size="large"
          prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
        />
      )}

      {/* Content */}
      {loading ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin size="large" />
        </div>
      ) : filteredAgents.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty
            image={<RobotOutlined style={{ fontSize: 56, color: '#d9d9d9' }} />}
            description={
              <span style={{ color: '#94a3b8', fontSize: 14 }}>
                {searchQuery ? 'No agents match your search' : 'No agents registered yet'}
              </span>
            }
          >
            {!searchQuery && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowModal(true)} size="large">
                Add Your First Agent
              </Button>
            )}
          </Empty>
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', paddingBottom: 16 }}>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: 16,
          }}>
            {paginatedAgents.map((agent, i) => (
              <Card
                key={agent.id}
                size="small"
                hoverable
                className="card-hover"
                style={{
                  animation: `fadeIn 0.3s ease-out ${i * 50}ms`,
                  borderRadius: 12,
                  border: '1px solid #f0f0f0',
                  overflow: 'hidden',
                  display: 'flex', flexDirection: 'column',
                }}
                styles={{
                  body: { padding: 0, flex: 1 },
                }}
                actions={[
                  <Tooltip title="Chat with this agent" key="chat">
                    <Button
                      type="text"
                      icon={<MessageOutlined />}
                      onClick={() => navigate(`/chat/${agent.id}`)}
                      style={{ color: '#10b981' }}
                    >
                      Chat
                    </Button>
                  </Tooltip>,
                  <Popconfirm
                    key="delete"
                    title="Delete agent?"
                    description={`Remove "${agent.name}"?`}
                    onConfirm={() => handleDelete(agent)}
                    okText="Delete"
                    cancelText="Cancel"
                    okButtonProps={{ danger: true }}
                  >
                    <Button type="text" danger icon={<DeleteOutlined />}>
                      Remove
                    </Button>
                  </Popconfirm>,
                ]}
              >
                {/* Top accent bar */}
                <div style={{
                  height: 3,
                  background: 'linear-gradient(90deg, #10b981, #34d399, #10b981)',
                }} />

                <div style={{ padding: 20 }}>
                  {/* Avatar + Name + URL */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                    <div style={{
                      width: 42, height: 42, borderRadius: 12,
                      background: 'linear-gradient(135deg, #34d399, #059669)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: 16, fontWeight: 700, flexShrink: 0,
                      boxShadow: '0 2px 8px rgba(16,185,129,0.2)',
                    }}>
                      {agent.name.charAt(0).toUpperCase()}
                    </div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{
                        fontWeight: 600, fontSize: 15, color: '#1e293b',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {agent.name}
                      </div>
                      <div style={{
                        fontSize: 12, color: '#94a3b8', fontFamily: "'JetBrains Mono', monospace",
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {agent.url.replace(/^https?:\/\//, '')}
                      </div>
                    </div>
                    {/* Status dot */}
                    <Tooltip title={agent.capabilities?.streaming ? 'Streaming enabled' : 'Standard'}>
                      <span className={`status-dot ${agent.capabilities?.streaming ? 'online' : 'offline'}`} />
                    </Tooltip>
                  </div>

                  {/* Version · Transport · Protocol · streaming */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#64748b',
                    marginBottom: 8, flexWrap: 'wrap',
                  }}>
                    {agent.version && (
                      <Tag style={{ fontSize: 10, lineHeight: '18px', padding: '0 6px', margin: 0, borderRadius: 4, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b' }}>
                        v{agent.version}
                      </Tag>
                    )}
                    {agent.preferredTransport && (
                      <Tag style={{ fontSize: 10, lineHeight: '18px', padding: '0 6px', margin: 0, borderRadius: 4, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b' }}>
                        {agent.preferredTransport}
                      </Tag>
                    )}
                    {agent.protocolVersion && (
                      <Tag style={{ fontSize: 10, lineHeight: '18px', padding: '0 6px', margin: 0, borderRadius: 4, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b' }}>
                        {agent.protocolVersion}
                      </Tag>
                    )}
                    {agent.capabilities?.streaming && (
                      <Tag color="green" style={{ fontSize: 10, lineHeight: '18px', padding: '0 6px', margin: 0, borderRadius: 4 }}>
                        <ThunderboltOutlined /> streaming
                      </Tag>
                    )}
                  </div>

                  {/* Modes + Description */}
                  <div style={{
                    fontSize: 13, color: '#64748b', marginBottom: 8, lineHeight: 1.5,
                  }}>
                    {agent.inputModes?.length > 0 && (
                      <span>
                        <span style={{ color: '#94a3b8', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>In: </span>
                        {agent.inputModes.join(', ')}
                        <span style={{ color: '#d1d5db', margin: '0 4px' }}>→</span>
                        <span style={{ color: '#94a3b8', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>Out: </span>
                        {agent.outputModes?.join(', ') || agent.inputModes.join(', ')}
                      </span>
                    )}
                  </div>

                  {agent.description && (
                    <div style={{
                      fontSize: 13, color: '#64748b', lineHeight: 1.5, marginBottom: 8,
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    }}>
                      {agent.description}
                    </div>
                  )}

                  {/* Skills */}
                  {agent.skills?.length > 0 && (
                    <div style={{ marginTop: 8, paddingTop: 12, borderTop: '1px solid #f1f5f9' }}>
                      <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
                        <TagsOutlined style={{ marginRight: 4 }} /> Skills
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {agent.skills.map((s, si) => (
                          <Tag key={si} style={{
                            fontSize: 11, lineHeight: '20px', padding: '0 8px', margin: 0,
                            borderRadius: 6, border: '1px solid #dbeafe', background: '#eff6ff', color: '#3b82f6',
                          }}>
                            {s.name || s.id}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {agents.length > pageSize && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 24 }}>
              <Pagination
                current={page}
                total={filteredAgents.length}
                pageSize={pageSize}
                onChange={setPage}
                showSizeChanger={false}
                showTotal={(total) => <span style={{ color: '#94a3b8', fontSize: 13 }}>{total} agents total</span>}
              />
            </div>
          )}
        </div>
      )}

      {/* Add Agent Modal */}
      <AddAgentModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onAdded={load}
      />
    </div>
  )
}

function AddAgentModal({ open, onClose, onAdded }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) { setUrl(''); setInfo(null); setError('') }
  }, [open])

  const handleFetch = async () => {
    if (!url.trim()) return
    setLoading(true); setError(''); setInfo(null)
    try {
      const card = await api.fetchAgentCard(url.trim())
      setInfo(card)
    } catch (e) {
      setError(e.message)
    } finally { setLoading(false) }
  }

  const handleSave = async () => {
    if (!url.trim()) return
    setLoading(true); setError('')
    try {
      await api.registerAgent(url.trim())
      message.success('Agent added!')
      onAdded()
      onClose()
    } catch (e) {
      setError(e.message)
    } finally { setLoading(false) }
  }

  return (
    <Modal
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 16 }}>
          <PlusOutlined style={{ color: '#10b981' }} />
          <span>Add A2A Agent</span>
        </div>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnClose
      style={{ borderRadius: 12 }}
    >
      <div style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 6, fontSize: 13, color: '#64748b', fontWeight: 500 }}>Agent URL</div>
        <Input.Search
          placeholder="e.g. localhost:10001 or https://example.com/agent"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setInfo(null); setError('') }}
          onSearch={handleFetch}
          enterButton={
            <Button
              type="default"
              loading={loading}
              style={{ borderRadius: '0 8px 8px 0', border: '1px solid #d9d9d9', borderLeft: 'none' }}
            >
              Fetch Card
            </Button>
          }
          disabled={loading}
          size="large"
          style={{ borderRadius: 8 }}
        />
      </div>

      {error && (
        <div style={{
          padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 8, color: '#dc2626', fontSize: 13, marginBottom: 12,
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <CloseCircleOutlined />
          {error}
        </div>
      )}

      {info && (
        <Card
          size="small"
          style={{
            marginBottom: 16, borderRadius: 10,
            background: 'linear-gradient(135deg, #f0fdf4, #ecfdf5)',
            border: '1px solid #bbf7d0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <CheckCircleOutlined style={{ color: '#10b981', fontSize: 16 }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: '#047857' }}>Agent Card Loaded</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #34d399, #059669)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 14, fontWeight: 700,
            }}>
              {info.name?.charAt(0)?.toUpperCase() || 'A'}
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>{info.name || 'N/A'}</div>
              {info.description && <div style={{ fontSize: 12, color: '#64748b' }}>{info.description}</div>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            <Tag style={{ borderRadius: 4, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b' }}>{info.version || 'v1.0'}</Tag>
            {info.capabilities?.streaming && <Tag color="green" style={{ borderRadius: 4 }}>Streaming</Tag>}
            {info.provider?.organization && <Tag style={{ borderRadius: 4, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b' }}>{info.provider.organization}</Tag>}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
        <Button onClick={onClose} style={{ borderRadius: 8 }}>Cancel</Button>
        {info && (
          <Button
            type="primary"
            onClick={handleSave}
            loading={loading}
            style={{ borderRadius: 8, paddingInline: 24, fontWeight: 600 }}
          >
            Add Agent
          </Button>
        )}
      </div>
    </Modal>
  )
}
