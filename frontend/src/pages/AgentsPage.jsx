import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Button, Modal, Input, Tag, Spin, Empty, Pagination, message, Tooltip, Popconfirm
} from 'antd'
import {
  PlusOutlined, MessageOutlined, DeleteOutlined, SearchOutlined,
  RobotOutlined, ApiOutlined, ThunderboltOutlined, TagsOutlined,
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

  return (
    <div style={{ padding: 32, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 20,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Agents</h2>
          <p style={{ margin: '4px 0 0', color: '#9ca3af', fontSize: 14 }}>
            {agents.length > 0
              ? `${filteredAgents.length} of ${agents.length} agents — Page ${page} of ${totalPages}`
              : 'No agents registered'}
          </p>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowModal(true)}>
          Add Agent
        </Button>
      </div>

      {/* Search */}
      {agents.length > 0 && (
        <Input.Search
          placeholder="Search agents by name, description, or skills..."
          allowClear
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1) }}
          onSearch={() => {}}
          style={{ marginBottom: 20 }}
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
            image={<RobotOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
            description={searchQuery ? 'No agents match your search' : 'No agents registered yet'}
          >
            {!searchQuery && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowModal(true)}>
                Add Your First Agent
              </Button>
            )}
          </Empty>
        </div>
      ) : (
        <div style={{ flex: 1, overflow: 'auto', paddingBottom: 16 }}>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
            gap: 16,
          }}>
            {paginatedAgents.map((agent, i) => (
              <Card
                key={agent.id}
                size="small"
                hoverable
                style={{ animation: `fadeIn 0.3s ease-out ${i * 50}ms`, borderLeft: '3px solid #10b981', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column' }}
                styles={{ body: { padding: 20, flex: 1 } }}
                actions={[
                  <Tooltip title="Chat" key="chat">
                    <MessageOutlined onClick={() => navigate(`/chat/${agent.id}`)} />
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
                    <DeleteOutlined style={{ color: '#ef4444' }} />
                  </Popconfirm>,
                ]}
              >
                {/* Avatar + Name + URL */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: 'linear-gradient(135deg, #34d399, #059669)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', fontSize: 14, fontWeight: 700, flexShrink: 0,
                  }}>
                    {agent.name.charAt(0).toUpperCase()}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {agent.name}
                    </div>
                    <div style={{ fontSize: 13, color: '#9ca3af', fontFamily: 'monospace' }}>
                      {agent.url.replace(/^https?:\/\//, '')}
                    </div>
                  </div>
                </div>

                {/* Version · Transport · Protocol · streaming */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#6b7280', marginBottom: 4, flexWrap: 'wrap' }}>
                  {agent.version && <><span style={{ fontFamily: 'monospace' }}>v{agent.version}</span><span style={{ color: '#d1d5db' }}>·</span></>}
                  {agent.preferredTransport && <><span>{agent.preferredTransport}</span><span style={{ color: '#d1d5db' }}>·</span></>}
                  {agent.protocolVersion && <><span>{agent.protocolVersion}</span></>}
                  {agent.capabilities?.streaming && (
                    <Tag color="green" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>streaming</Tag>
                  )}
                </div>

                {/* Modes + Description */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: '#9ca3af', flexWrap: 'wrap', marginBottom: 4 }}>
                  {agent.inputModes?.length > 0 && (
                    <span>{agent.inputModes.join(', ')} <span style={{ color: '#d1d5db' }}>→</span> {agent.outputModes?.join(', ') || agent.inputModes.join(', ')}</span>
                  )}
                  {(agent.inputModes?.length > 0 || agent.outputModes?.length > 0) && agent.description && (
                    <span style={{ color: '#d1d5db' }}>|</span>
                  )}
                  {agent.description && <span>{agent.description}</span>}
                </div>

                {/* Skills */}
                {agent.skills?.length > 0 && (
                  <div style={{ fontSize: 13, color: '#6b7280', marginTop: 6 }}>
                    <TagsOutlined style={{ marginRight: 4 }} />
                    {agent.skills.map((s, si) => (
                      <Tag key={si} style={{ fontSize: 10, lineHeight: '16px', marginBottom: 2 }}>{s.name || s.id}</Tag>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {agents.length > pageSize && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
              <Pagination
                current={page}
                total={filteredAgents.length}
                pageSize={pageSize}
                onChange={setPage}
                showSizeChanger={false}
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
      title={<><PlusOutlined /> Add A2A Agent</>}
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnClose
    >
      <div style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 4, fontSize: 13, color: '#6b7280' }}>Agent URL</div>
        <Input.Search
          placeholder="localhost:10001"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setInfo(null); setError('') }}
          onSearch={handleFetch}
          enterButton={info ? null : <Button type="default" loading={loading}>Fetch</Button>}
          disabled={loading}
        />
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {info && (
        <Card size="small" style={{ marginBottom: 12, background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981' }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#047857' }}>Agent Card Loaded</span>
          </div>
          <p style={{ margin: '2px 0', fontSize: 13 }}><span style={{ color: '#9ca3af' }}>Name:</span> <strong>{info.name || 'N/A'}</strong></p>
          {info.description && <p style={{ margin: '2px 0', fontSize: 13, color: '#6b7280' }}>{info.description}</p>}
          <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
            <Tag>{info.version || 'v1.0'}</Tag>
            {info.capabilities?.streaming && <Tag color="green">Streaming</Tag>}
            {info.provider?.organization && <Tag>{info.provider.organization}</Tag>}
          </div>
        </Card>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button onClick={onClose}>Cancel</Button>
        {info && (
          <Button type="primary" onClick={handleSave} loading={loading}>
            Add Agent
          </Button>
        )}
      </div>
    </Modal>
  )
}
