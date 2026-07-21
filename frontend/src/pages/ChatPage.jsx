import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Select, Button, Input, Tag, Spin, Empty, Typography, message, Drawer, Tooltip, Badge, Avatar, Dropdown,
} from 'antd'
import {
  PlusOutlined, SendOutlined, DeleteOutlined, FileTextOutlined,
  RobotOutlined, UserOutlined, LoadingOutlined, MessageOutlined,
  EllipsisOutlined, HistoryOutlined, ClearOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'

const { Text } = Typography
const { TextArea } = Input

/* ───────── Typing Indicator ───────── */
function TypingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
      <div style={{
        width: 30, height: 30, borderRadius: 8, flexShrink: 0, marginBottom: 2,
        background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontSize: 12, fontWeight: 600,
      }}>A</div>
      <div style={{
        padding: '14px 18px',
        borderRadius: '14px 14px 14px 4px',
        background: '#fff',
        border: '1px solid #e5e7eb',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  )
}

/* ───────── Message Bubble ───────── */
function MessageBubble({ msg, agentName }) {
  const isUser = msg.role === 'user'
  const displayName = isUser ? 'You' : (agentName || 'Assistant')

  return (
    <div style={{
      display: 'flex', gap: 10,
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      alignItems: 'flex-end', marginBottom: 16,
      animation: isUser ? 'slideInRight 0.3s ease-out' : 'slideInLeft 0.3s ease-out',
    }}>
      {!isUser && (
        <Avatar
          size={34}
          style={{
            background: 'linear-gradient(135deg, #10b981, #059669)',
            flexShrink: 0, marginBottom: 2,
            boxShadow: '0 2px 8px rgba(16,185,129,0.2)',
            fontSize: 14, fontWeight: 700,
          }}
        >
          {displayName.charAt(0).toUpperCase()}
        </Avatar>
      )}
      <div style={{ maxWidth: '72%' }}>
        {!isUser && (
          <div style={{
            fontSize: 11, color: '#10b981', fontWeight: 600,
            marginBottom: 4, marginLeft: 4, letterSpacing: 0.2,
          }}>
            {displayName}
          </div>
        )}
        <div style={{
          padding: '12px 18px',
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          background: isUser
            ? 'linear-gradient(135deg, #3b82f6, #2563eb)'
            : '#ffffff',
          color: isUser ? '#fff' : '#1e293b',
          border: isUser ? 'none' : '1px solid #e5e7eb',
          boxShadow: isUser
            ? '0 4px 14px rgba(59,130,246,0.2)'
            : '0 2px 8px rgba(0,0,0,0.04)',
        }}>
          <div className="markdown" style={{ fontSize: 14, lineHeight: 1.7 }}>
            {msg.content}
          </div>
        </div>
      </div>
      {isUser && (
        <Avatar
          size={34}
          style={{
            background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
            flexShrink: 0, marginBottom: 2,
            boxShadow: '0 2px 8px rgba(59,130,246,0.2)',
          }}
          icon={<UserOutlined />}
        />
      )}
    </div>
  )
}

/* ───────── Floating Events Drawer ───────── */
function EventsDrawer({ conversationId }) {
  const [events, setEvents] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (conversationId && open) {
      api.queryEvents(conversationId).then(setEvents).catch(() => {})
    }
  }, [conversationId, open])

  return (
    <>
      <Tooltip title="Task Events">
        <Button
          type="default"
          icon={<FileTextOutlined />}
          onClick={() => setOpen(true)}
          style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 100,
            width: 44, height: 44, borderRadius: 12,
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            border: '1px solid #e5e7eb',
            background: '#fff',
          }}
        />
      </Tooltip>
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileTextOutlined style={{ color: '#10b981' }} />
            <span>Task Events</span>
            <Tag style={{ marginLeft: 8, borderRadius: 10 }}>{events.length}</Tag>
          </div>
        }
        placement="right"
        width={380}
        onClose={() => setOpen(false)}
        open={open}
        style={{ borderRadius: '12px 0 0 12px' }}
      >
        {events.length === 0 ? (
          <Empty description="No events yet" />
        ) : (
          events.map((e) => (
            <div key={e.id} style={{
              padding: '10px 0', borderBottom: '1px solid #f0f0f0',
              animation: 'fadeIn 0.3s ease-out',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Tag color={e.state === 'completed' ? 'green' : e.state === 'failed' ? 'red' : e.state === 'working' ? 'orange' : 'default'}
                  style={{ fontSize: 10, margin: 0, borderRadius: 4 }}>
                  {e.state}
                </Tag>
                <Text type="secondary" style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>{e.event_type}</Text>
              </div>
              <Text type="secondary" style={{ fontSize: 12, color: '#64748b' }} ellipsis>
                {e.content?.slice(0, 120)}
              </Text>
            </div>
          ))
        )}
      </Drawer>
    </>
  )
}

/* ───────── Main Chat Page ───────── */
export default function ChatPage() {
  const { agentId: urlAgentId } = useParams()
  const navigate = useNavigate()
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const [agents, setAgents] = useState([])
  const [agentId, setAgentId] = useState(urlAgentId || '')
  const [currentAgentName, setCurrentAgentName] = useState('')
  const [conversations, setConversations] = useState([])
  const [currentConvId, setCurrentConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [convLoading, setConvLoading] = useState(false)
  const [msgLoading, setMsgLoading] = useState(false)

  // Load agents
  useEffect(() => { api.listAgents().then(setAgents).catch(() => {}) }, [])

  // Update agent ID from URL
  useEffect(() => {
    if (urlAgentId) setAgentId(urlAgentId)
  }, [urlAgentId])

  // Update agent name when agent changes
  useEffect(() => {
    if (agentId) {
      const agent = agents.find(a => a.id === agentId)
      if (agent) setCurrentAgentName(agent.name)
    } else {
      setCurrentAgentName('')
    }
  }, [agentId, agents])

  // Load conversations for this agent
  useEffect(() => {
    if (!agentId) { setConversations([]); setCurrentConvId(null); setMessages([]); return }
    api.listConversations(agentId).then(convs => {
      setConversations(convs)
      if (convs.length > 0) {
        const latest = convs[0]
        setCurrentConvId(latest.id)
      } else {
        setCurrentConvId(null)
        setMessages([])
      }
    }).catch(() => {})
  }, [agentId])

  // Load messages for selected conversation
  useEffect(() => {
    if (!currentConvId) { setMessages([]); return }
    setMsgLoading(true)
    api.getConversation(currentConvId).then(conv => {
      setMessages(conv?.messages || [])
    }).catch(() => {}).finally(() => setMsgLoading(false))
  }, [currentConvId])

  // Auto scroll
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const handleNewConversation = useCallback(async () => {
    if (!agentId) return
    try {
      const conv = await api.createConversation(agentId, 'New Chat', 'single')
      setConversations(prev => [conv, ...prev])
      setCurrentConvId(conv.id)
      setMessages([])
    } catch {}
  }, [agentId])

  const handleDeleteConv = useCallback(async (convId) => {
    try {
      await api.deleteConversation(convId)
      setConversations(prev => prev.filter(c => c.id !== convId))
      if (currentConvId === convId) {
        setCurrentConvId(null)
        setMessages([])
      }
    } catch {}
  }, [currentConvId])

  const handleSelectAgent = useCallback((id) => {
    setAgentId(id)
    navigate(`/chat/${id}`)
  }, [navigate])

  const handleSelectConv = useCallback((convId) => {
    setCurrentConvId(convId)
  }, [])

  const handleSend = useCallback(async () => {
    const text = inputText.trim()
    if (!text || sending || !currentConvId) return
    setInputText('')
    setSending(true)

    const userMsg = { role: 'user', content: text, id: `opt-${Date.now()}` }
    const agentMsg = { role: 'agent', content: '', id: `agent-${Date.now()}`, loading: true }
    setMessages(prev => [...prev, userMsg, agentMsg])

    let accumulated = ''
    api.sendMessageStream(currentConvId, text,
      (evt) => {
        if (evt.text) {
          accumulated += evt.text
          setMessages(prev => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            if (last && last.role === 'agent' && last.loading) {
              copy[copy.length - 1] = { ...last, content: accumulated }
            }
            return copy
          })
        }
      },
      (error) => {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = { ...last, content: `Error: ${error}`, loading: false }
          }
          return copy
        })
        setSending(false)
      },
      () => {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = { ...last, loading: false }
          }
          return copy
        })
        setSending(false)
        api.getConversation(currentConvId).then(conv => {
          setMessages(conv?.messages || [])
        }).catch(() => {})
        api.listConversations(agentId).then(setConversations).catch(() => {})
      }
    )
  }, [inputText, sending, currentConvId, agentId])

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#f8fafc' }}>
      {/* Left sidebar */}
      <div style={{
        width: 280, borderRight: '1px solid #e5e7eb', background: '#fff',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
      }}>
        {/* Agent selector */}
        <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid #f1f5f9' }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            <RobotOutlined style={{ marginRight: 4 }} /> Agent
          </Text>
          <Select
            value={agentId || undefined}
            onChange={handleSelectAgent}
            placeholder="Select an agent"
            style={{ width: '100%' }}
            options={agents.map(a => ({ value: a.id, label: a.name }))}
            size="large"
          />
        </div>

        {/* New chat button */}
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #f1f5f9' }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={handleNewConversation}
            disabled={!agentId}
            style={{ borderRadius: 8, height: 38, fontWeight: 600 }}
          >
            New Chat
          </Button>
        </div>

        {/* Conversation list header */}
        <div style={{
          padding: '10px 16px 6px',
          fontSize: 11, color: '#94a3b8', fontWeight: 500,
          textTransform: 'uppercase', letterSpacing: 0.5,
        }}>
          <HistoryOutlined style={{ marginRight: 4 }} /> Conversations
        </div>

        {/* Conversation list */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12, color: '#94a3b8' }}>
                {agentId ? 'No conversations yet' : 'Select an agent first'}
              </Text>
            </div>
          ) : (
            conversations.map(c => (
              <div
                key={c.id}
                onClick={() => handleSelectConv(c.id)}
                style={{
                  padding: '12px 16px', cursor: 'pointer',
                  borderLeft: currentConvId === c.id ? '3px solid #10b981' : '3px solid transparent',
                  background: currentConvId === c.id ? '#f0fdf4' : 'transparent',
                  borderBottom: '1px solid #f8fafc',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => { if (currentConvId !== c.id) e.currentTarget.style.background = '#f8fafc' }}
                onMouseLeave={(e) => { if (currentConvId !== c.id) e.currentTarget.style.background = 'transparent' }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    fontWeight: currentConvId === c.id ? 600 : 400,
                    fontSize: 13, color: '#1e293b',
                  }}>
                    {c.title}
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                    {c.message_count || 0} messages
                  </div>
                </div>
                <DeleteOutlined
                  style={{ color: '#d1d5db', fontSize: 12, cursor: 'pointer', flexShrink: 0, marginLeft: 8 }}
                  onClick={(e) => { e.stopPropagation(); handleDeleteConv(c.id) }}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {currentConvId ? (
          <>
            {/* Agent info bar */}
            <div style={{
              padding: '12px 24px', borderBottom: '1px solid #e5e7eb',
              background: '#fff', display: 'flex', alignItems: 'center', gap: 10,
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}>
              <Badge status="success" dot>
                <Avatar
                  size={32}
                  style={{
                    background: 'linear-gradient(135deg, #10b981, #059669)',
                    fontSize: 13, fontWeight: 700,
                    boxShadow: '0 2px 6px rgba(16,185,129,0.2)',
                  }}
                >
                  {currentAgentName ? currentAgentName.charAt(0).toUpperCase() : 'A'}
                </Avatar>
              </Badge>
              <div>
                <Text strong style={{ fontSize: 14, color: '#1e293b' }}>{currentAgentName || 'Agent'}</Text>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>Online</div>
              </div>
            </div>

            {/* Messages */}
            <div style={{
              flex: 1, overflow: 'auto', padding: '24px 32px',
              background: '#fafbfc',
            }}>
              {msgLoading ? (
                <div style={{ textAlign: 'center', padding: 60 }}>
                  <Spin size="large" />
                </div>
              ) : messages.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                  <Empty
                    image={<MessageOutlined style={{ fontSize: 56, color: '#d9d9d9' }} />}
                    description={
                      <span style={{ color: '#94a3b8', fontSize: 14 }}>
                        Start a conversation with {currentAgentName || 'the agent'}
                      </span>
                    }
                  />
                </div>
              ) : (
                <div style={{ maxWidth: 800, margin: '0 auto' }}>
                  {messages.map((m) => (
                    m.content || m.loading ? <MessageBubble key={m.id} msg={m} agentName={currentAgentName} /> : null
                  ))}
                </div>
              )}

              {sending && !messages.some(m => m.role === 'agent' && m.loading) && (
                <div style={{ maxWidth: 800, margin: '0 auto' }}>
                  <TypingIndicator />
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{
              borderTop: '1px solid #e5e7eb', padding: '16px 24px',
              background: '#fff',
            }}>
              <div style={{ display: 'flex', gap: 10, maxWidth: 800, margin: '0 auto' }}>
                <TextArea
                  ref={inputRef}
                  rows={1}
                  placeholder="Type a message..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend() } }}
                  disabled={sending}
                  style={{
                    borderRadius: 12, paddingLeft: 18, paddingRight: 18,
                    paddingTop: 12, paddingBottom: 12,
                    fontSize: 14, border: '1px solid #e2e8f0',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                    resize: 'none',
                  }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  shape="circle"
                  size="large"
                  onClick={handleSend}
                  disabled={sending || !inputText.trim()}
                  style={{
                    width: 48, height: 48, flexShrink: 0,
                    boxShadow: sending || !inputText.trim() ? 'none' : '0 4px 12px rgba(16,185,129,0.3)',
                  }}
                />
              </div>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Empty
              image={<MessageOutlined style={{ fontSize: 56, color: '#d9d9d9' }} />}
              description={
                <span style={{ color: '#94a3b8', fontSize: 14 }}>
                  Select or create a conversation
                </span>
              }
            >
              {agentId && (
                <Button type="primary" icon={<PlusOutlined />} onClick={handleNewConversation} size="large">
                  New Chat
                </Button>
              )}
            </Empty>
          </div>
        )}
      </div>

      <EventsDrawer conversationId={currentConvId} />
    </div>
  )
}
