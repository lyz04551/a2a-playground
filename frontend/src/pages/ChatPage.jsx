import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Select, Button, Input, Tag, Spin, Empty, Typography, message, Drawer, Tooltip,
} from 'antd'
import {
  PlusOutlined, SendOutlined, DeleteOutlined, FileTextOutlined,
  RobotOutlined, UserOutlined, LoadingOutlined, MessageOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'

const { Text } = Typography
const { TextArea } = Input

/* ───────── Message Bubble ───────── */
function MessageBubble({ msg, agentName }) {
  const isUser = msg.role === 'user'
  const displayName = isUser ? 'You' : (agentName || 'Assistant')
  const icon = isUser ? <UserOutlined /> : (displayName.charAt(0).toUpperCase())
  const bgColor = isUser ? 'linear-gradient(135deg, #3b82f6, #2563eb)' : '#10b981'

  return (
    <div style={{
      display: 'flex', gap: 8, justifyContent: isUser ? 'flex-end' : 'flex-start',
      alignItems: 'flex-end', marginBottom: 12, animation: 'fadeIn 0.3s ease-out',
    }}>
      {!isUser && (
        <div style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, marginBottom: 2,
          background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 12, fontWeight: 600,
        }}>{icon}</div>
      )}
      <div style={{ maxWidth: '75%' }}>
        {!isUser && (
          <div style={{ fontSize: 11, color: '#10b981', fontWeight: 600, marginBottom: 4, marginLeft: 2 }}>
            {displayName}
          </div>
        )}
        <div style={{
          padding: '12px 16px',
          borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
          background: isUser
            ? 'linear-gradient(135deg, #3b82f6, #2563eb)'
            : '#fff',
          color: isUser ? '#fff' : '#1f2937',
          border: isUser ? 'none' : '1px solid #e5e7eb',
          boxShadow: isUser ? '0 2px 8px rgba(59,130,246,0.2)' : '0 1px 4px rgba(0,0,0,0.04)',
        }}>
          <div className="markdown" style={{ fontSize: 15, lineHeight: 1.7 }}>
            {msg.content}
          </div>
        </div>
      </div>
      {isUser && (
        <div style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, marginBottom: 2,
          background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 12, fontWeight: 600,
        }}>
          <UserOutlined />
        </div>
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
          type="default" shape="circle" icon={<FileTextOutlined />}
          onClick={() => setOpen(true)}
          style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 100 }}
        />
      </Tooltip>
      <Drawer
        title={`Task Events (${events.length})`} placement="right" width={360}
        onClose={() => setOpen(false)} open={open}
      >
        {events.length === 0 ? (
          <Empty description="No events yet" />
        ) : (
          events.map((e) => (
            <div key={e.id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0', fontSize: 13 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Tag color={e.state === 'completed' ? 'green' : e.state === 'failed' ? 'red' : e.state === 'working' ? 'orange' : 'default'}
                  style={{ fontSize: 10, margin: 0 }}>
                  {e.state}
                </Tag>
                <Text type="secondary" style={{ fontSize: 11 }}>{e.event_type}</Text>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
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
      // Auto-select the most recent conversation
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

    // Add user message to UI
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
        // Reload from backend
        api.getConversation(currentConvId).then(conv => {
          setMessages(conv?.messages || [])
        }).catch(() => {})
        // Update conversation list
        api.listConversations(agentId).then(setConversations).catch(() => {})
      }
    )
  }, [inputText, sending, currentConvId, agentId])

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#f5f5f5' }}>
      {/* Left sidebar */}
      <div style={{
        width: 280, borderRight: '1px solid #e5e7eb', background: '#fff',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Agent selector */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Agent</Text>
          <Select
            value={agentId || undefined}
            onChange={handleSelectAgent}
            placeholder="Select an agent"
            style={{ width: '100%' }}
            options={agents.map(a => ({ value: a.id, label: a.name }))}
          />
        </div>

        {/* New chat button */}
        <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
          <Button type="primary" icon={<PlusOutlined />} block onClick={handleNewConversation}
            disabled={!agentId}>
            New Chat
          </Button>
        </div>

        {/* Conversation list */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {agentId ? 'No conversations yet' : 'Select an agent first'}
              </Text>
            </div>
          ) : (
            conversations.map(c => (
              <div
                key={c.id}
                onClick={() => handleSelectConv(c.id)}
                style={{
                  padding: '10px 16px', cursor: 'pointer',
                  borderLeft: currentConvId === c.id ? '3px solid #3b82f6' : '3px solid transparent',
                  background: currentConvId === c.id ? '#eff6ff' : 'transparent',
                  borderBottom: '1px solid #f0f0f0',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    fontWeight: currentConvId === c.id ? 600 : 400,
                  }}>
                    {c.title}
                  </div>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
                    {c.message_count || 0} messages
                  </div>
                </div>
                <DeleteOutlined
                  style={{ color: '#d1d5db', fontSize: 13, cursor: 'pointer', flexShrink: 0 }}
                  onClick={(e) => { e.stopPropagation(); handleDeleteConv(c.id) }}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {currentConvId ? (
          <>
            {/* Agent info bar */}
            <div style={{
              padding: '10px 20px', borderBottom: '1px solid #e5e7eb', background: '#fff',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 6,
                background: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 12, fontWeight: 600,
              }}>
                {currentAgentName ? currentAgentName.charAt(0).toUpperCase() : 'A'}
              </div>
              <Text strong style={{ fontSize: 14 }}>{currentAgentName || 'Agent'}</Text>
            </div>

            {/* Messages */}
            <div style={{
              flex: 1, overflow: 'auto', padding: '24px 32px',
              background: '#fafbfc',
            }}>
              {msgLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              ) : messages.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                  <Empty description="Start a conversation" />
                </div>
              ) : (
                messages.map((m) => (
                  m.content || m.loading ? <MessageBubble key={m.id} msg={m} agentName={currentAgentName} /> : null
                ))
              )}

              {sending && !messages.some(m => m.role === 'agent' && m.loading) && (
                <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
                  <div style={{
                    padding: '10px 14px', borderRadius: '14px 14px 14px 4px',
                    background: '#fff', border: '1px solid #e5e7eb', boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <LoadingOutlined style={{ color: '#9ca3af' }} />
                      <Text type="secondary" style={{ fontSize: 12 }}>thinking...</Text>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{ borderTop: '1px solid #e5e7eb', padding: 12, background: '#fff' }}>
              <div style={{ display: 'flex', gap: 8, maxWidth: 800, margin: '0 auto' }}>
                <TextArea
                  ref={inputRef}
                  rows={1}
                  placeholder="Type a message..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend() } }}
                  disabled={sending}
                  style={{ borderRadius: 12, paddingLeft: 16, paddingRight: 16 }}
                />
                <Button
                  type="primary" icon={<SendOutlined />} shape="circle" size="large"
                  onClick={handleSend}
                  disabled={sending || !inputText.trim()} style={{ width: 44, height: 44 }}
                />
              </div>
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Empty
              image={<MessageOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
              description="Select or create a conversation"
            >
              {agentId && (
                <Button type="primary" icon={<PlusOutlined />} onClick={handleNewConversation}>
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
