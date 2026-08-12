import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Input, Spin, Empty, Pagination, message } from 'antd'
import {
  PlusOutlined, SearchOutlined, RobotOutlined, ReloadOutlined,
} from '@ant-design/icons'
import AgentDetailDrawer from '../components/AgentDetailDrawer'
import AddAgentModal from '../components/agents/AddAgentModal'
import AgentCard from '../components/agents/AgentCard'
import AgentStats from '../components/agents/AgentStats'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'
import { agentStats, filterAgents } from '../state/agentHealth'
import useAgents from '../hooks/useAgents'

export default function AgentsPage() {
  const navigate = useNavigate()
  const { settings } = useConsoleSettings()
  const zh = settings.language === 'zh-CN'
  const { agents, healthMap, loading, healthLoading, error, clearError, load, checkHealth, remove } = useAgents()
  const [showModal, setShowModal] = useState(false)
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedAgent, setSelectedAgent] = useState(null)
  const pageSize = 9

  const filteredAgents = filterAgents(agents, searchQuery)

  const paginatedAgents = filteredAgents.slice((page - 1) * pageSize, page * pageSize)

  useEffect(() => { setPage(1) }, [agents.length])

  const handleDelete = async (agent) => {
    try {
      await remove(agent.id)
      message.success(zh ? `已移除 ${agent.name}` : `Removed ${agent.name}`)
    } catch { message.error(zh ? '删除智能体失败' : 'Failed to delete agent') }
  }

  // Stats
  const stats = agentStats(agents, healthMap)

  return (
    <div className="agents-page">
      {/* Header */}
      <div className="agents-header">
        <div>
          <h2>{zh ? '智能体' : 'Agents'}</h2>
          <p>
            {zh ? '管理并监控 A2A 智能体' : 'Manage and monitor your A2A agents'}
          </p>
        </div>
        <div className="agents-header-actions">
          <Button
            icon={<ReloadOutlined spin={healthLoading} />}
            onClick={checkHealth}
            size="large"
            loading={healthLoading}
          >
            {healthLoading ? (zh ? '检查中…' : 'Checking...') : (zh ? '健康检查' : 'Health Check')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setShowModal(true)}
            size="large"
          >
            {zh ? '添加智能体' : 'Add Agent'}
          </Button>
        </div>
      </div>
      {error && <Alert closable onClose={clearError} type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {agents.length > 0 && <AgentStats stats={stats} zh={zh} />}

      {/* Search */}
      {agents.length > 0 && (
        <Input.Search
          placeholder={zh ? '按名称、描述或 Skill 搜索…' : 'Search agents by name, description, or skills...'}
          allowClear
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1) }}
          onSearch={() => { }}
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
                {searchQuery ? (zh ? '没有符合搜索条件的智能体' : 'No agents match your search') : (zh ? '尚未注册智能体' : 'No agents registered yet')}
              </span>
            }
          >
            {!searchQuery && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowModal(true)} size="large">
                {zh ? '添加第一个智能体' : 'Add your first agent'}
              </Button>
            )}
          </Empty>
        </div>
      ) : (
        <div className="agents-content">
          <div className="agents-grid">
            {paginatedAgents.map((agent, index) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                health={healthMap[agent.id]}
                index={index}
                zh={zh}
                onOpen={() => setSelectedAgent(agent)}
                onChat={() => navigate(`/workspace?mode=direct&agent=${encodeURIComponent(agent.id)}`)}
                onDelete={() => handleDelete(agent)}
              />
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
                showTotal={(total) => <span>{zh ? `共 ${total} 个智能体` : `${total} agents total`}</span>}
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
        zh={zh}
      />
      <AgentDetailDrawer agent={selectedAgent} health={selectedAgent ? healthMap[selectedAgent.id] : null} open={Boolean(selectedAgent)} onClose={() => setSelectedAgent(null)} onTest={checkHealth} testing={healthLoading} zh={zh} />
    </div>
  )
}
