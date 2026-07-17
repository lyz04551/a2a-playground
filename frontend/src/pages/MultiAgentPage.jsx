import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Button, Input, Tag, Spin, Empty, Typography, Tooltip, Drawer } from 'antd'
import {
  SendOutlined, ApiOutlined, CodeOutlined, CheckCircleOutlined,
  SyncOutlined, PlusOutlined, DeleteOutlined, FileTextOutlined,
  UserOutlined, RobotOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'

const { Text } = Typography
const { TextArea } = Input

/* ───────── Agent colors ───────── */
const AGENT_COLORS = ['#10b981', '#6366f1', '#f59e0b', '#ef4444', '#06b5ce', '#8b5cf6', '#ec4899', '#14b8a6']
function getAgentColor(name) {
  if (!name) return '#10b981'
  if (name === 'Host Agent') return '#10b981'
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length]
}

/* ───────── Tool Call Card ───────── */
function ToolCallCard({ toolCall, toolResult }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{
      marginBottom: 10, animation: 'fadeIn 0.3s ease-out',
      background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0',
      overflow: 'hidden', fontSize: 12,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
        cursor: 'pointer', borderBottom: expanded ? '1px solid #e2e8f0' : 'none',
      }} onClick={() => setExpanded(!expanded)}>
        <CodeOutlined style={{ color: '#6366f1', fontSize: 13 }} />
        <span style={{ fontWeight: 600, color: '#374151' }}>{toolCall.tool}</span>
        {toolResult ? (
          <CheckCircleOutlined style={{ color: '#10b981', fontSize: 12, marginLeft: 'auto' }} />
        ) : (
          <SyncOutlined spin style={{ color: '#f59e0b', fontSize: 12, marginLeft: 'auto' }} />
        )}
      </div>
      {expanded && (
        <div style={{ padding: '6px 10px' }}>
          {toolCall.args && Object.keys(toolCall.args).length > 0 && (
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>Args:</Text>
              <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', color: '#6b7280' }}>
                {JSON.stringify(toolCall.args, null, 2)}
              </pre>
            </div>
          )}
          {toolResult && (
            <div>
              <Text type="secondary" style={{ fontSize: 11 }}>Result:</Text>
              <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', color: '#374151', maxHeight: 200, overflow: 'auto' }}>
                {typeof toolResult === 'string' ? toolResult.slice(0, 500) : JSON.stringify(toolResult, null, 2).slice(0, 500)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ───────── Message Bubble ───────── */
function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'
  const agentName = msg.routingAgent || msg.metadata?.routing_agent || 'Host Agent'
  const agentIcon = agentName.charAt(0).toUpperCase()
  const agentColor = getAgentColor(agentName)
  const toolCalls = msg.toolCalls || msg.metadata?.tool_calls || []
  const toolResults = msg.toolResults || msg.metadata?.tool_results || {}

  return (
    <div style={{ marginBottom: 16, animation: 'fadeIn 0.3s ease-out' }}>
      {/* Tool calls above the agent message */}
      {!isUser && toolCalls && toolCalls.map((tc, i) => (
        <ToolCallCard key={tc.id || i} toolCall={tc} toolResult={toolResults?.[tc.id] || null} />
      ))}
      <div style={{ display: 'flex', gap: 8, justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
        {!isUser && (
          <div style={{
            width: 32, height: 32, borderRadius: 8, flexShrink: 0, marginTop: 4,
            background: agentColor,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 14, fontWeight: 700, boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
          }}>
            {agentIcon}
          </div>
        )}
        <div style={{ maxWidth: '72%' }}>
          {!isUser && (
            <div style={{ fontSize: 12, color: agentColor, fontWeight: 600, marginBottom: 4, marginLeft: 2 }}>
              {agentName}
            </div>
          )}
          <div style={{
            padding: '12px 16px',
            borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            background: isUser ? 'linear-gradient(135deg, #10b981, #059669)' : '#fff',
            color: isUser ? '#fff' : '#1f2937',
            border: isUser ? 'none' : '1px solid #e5e7eb',
            boxShadow: isUser ? '0 2px 12px rgba(16,185,129,0.15)' : '0 2px 8px rgba(0,0,0,0.04)',
          }}>
            <div className="markdown" style={{ fontSize: 15, lineHeight: 1.7 }}>{msg.content}</div>
          </div>
        </div>
        {isUser && (
          <div style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0, marginTop: 4,
            background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff', fontSize: 13, fontWeight: 600,
          }}>
            <UserOutlined />
          </div>
        )}
      </div>
    </div>
  )
}

/* ───────── Events Drawer ───────── */
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
      <Drawer title={`Task Events (${events.length})`} placement="right" width={400}
        onClose={() => setOpen(false)} open={open}
      >
        {events.length === 0 ? (
          <Empty description="No events yet" />
        ) : (
          events.map((e) => {
            let content = e.content
            try { content = JSON.parse(e.content) } catch {}
            return (
              <div key={e.id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0', fontSize: 13 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Tag color={e.event_type === 'tool_call' ? 'blue' : e.event_type === 'tool_result' ? 'green' : e.event_type === 'routing' ? 'purple' : 'default'}
                    style={{ fontSize: 10, margin: 0 }}>
                    {e.event_type}
                  </Tag>
                  <Tag color={e.state === 'completed' ? 'green' : e.state === 'failed' ? 'red' : 'orange'}
                    style={{ fontSize: 10, margin: 0 }}>
                    {e.state}
                  </Tag>
                </div>
                <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', color: '#6b7280', maxHeight: 120, overflow: 'auto' }}>
                  {typeof content === 'string' ? content.slice(0, 200) : JSON.stringify(content, null, 2).slice(0, 200)}
                </pre>
              </div>
            )
          })
        )}
      </Drawer>
    </>
  )
}

/* ───────── Main Multi-Agent Page ───────── */
export default function MultiAgentPage() {
  const messagesEndRef = useRef(null)
  const [agents, setAgents] = useState([])
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [conversations, setConversations] = useState([])
  const [currentConvId, setCurrentConvId] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [convLoading, setConvLoading] = useState(false)

  // Load agents
  useEffect(() => { api.hostAgents().then(setAgents).catch(() => {}) }, [])

  // Auto scroll
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // Load multi-agent conversations
  const loadConversations = useCallback(async () => {
    try {
      const convs = await api.listConversationsByType('multi')
      setConversations(convs)
    } catch {}
  }, [])

  useEffect(() => { loadConversations() }, [loadConversations])

  // Load messages for a conversation
  const loadMessages = useCallback(async (convId) => {
    if (!convId) return
    setConvLoading(true)
    try {
      const conv = await api.getConversation(convId)
      if (conv?.messages) {
        setMessages(conv.messages)
        setCurrentConvId(convId)
      }
    } catch {}
    setConvLoading(false)
  }, [])

  // Create new conversation
  const handleNewConversation = useCallback(async () => {
    try {
      const conv = await api.createConversation('multi-host', 'Multi-Agent Chat', 'multi')
      setCurrentConvId(conv.id)
      setMessages([])
      setSessionId('')
      loadConversations()
    } catch {}
  }, [loadConversations])

  // Delete conversation
  const handleDeleteConv = useCallback(async (convId) => {
    try {
      await api.deleteConversation(convId)
      if (currentConvId === convId) {
        setCurrentConvId('')
        setMessages([])
        setSessionId('')
      }
      loadConversations()
    } catch {}
  }, [currentConvId, loadConversations])

  // Send message
  const handleSend = useCallback(async () => {
    const text = inputText.trim()
    if (!text || sending) return
    setInputText('')
    setSending(true)

    // Ensure we have a conversation
    let convId = currentConvId
    if (!convId) {
      try {
        const conv = await api.createConversation('multi-host', 'Multi-Agent Chat', 'multi')
        convId = conv.id
        setCurrentConvId(convId)
        loadConversations()
      } catch {
        setSending(false)
        return
      }
    }

    const sid = sessionId || `session-${Date.now()}`
    if (!sessionId) setSessionId(sid)

    // Add user message to UI immediately
    const userMsg = { role: 'user', content: text, id: `opt-${Date.now()}` }
    const agentMsg = { role: 'agent', content: '', id: `agent-${Date.now()}`, loading: true, routingAgent: 'Host Agent' }
    setMessages(prev => [...prev, userMsg, agentMsg])

    const toolCalls = []
    const toolResults = {}
    let currentRouting = 'Host Agent'

    api.hostLgSendStream(
      text, sid, convId,
      // onEvent (text)
      (evt) => {
        if (evt.text) {
          setMessages(prev => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            if (last && last.role === 'agent' && last.loading) {
              copy[copy.length - 1] = { ...last, content: last.content + evt.text, routingAgent: currentRouting }
            }
            return copy
          })
        }
      },
      // onToolCall
      (evt) => {
        toolCalls.push({ tool: evt.tool, args: evt.args, id: evt.id })
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = { ...last, toolCalls: [...toolCalls], toolResults: { ...toolResults }, routingAgent: currentRouting }
          }
          return copy
        })
      },
      // onToolResult
      (evt) => {
        toolResults[evt.id] = evt.result
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = { ...last, toolCalls: [...toolCalls], toolResults: { ...toolResults }, routingAgent: currentRouting }
          }
          return copy
        })
      },
      // onRouting
      (evt) => {
        currentRouting = evt.agent || 'Host Agent'
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = { ...last, routingAgent: currentRouting }
          }
          return copy
        })
      },
      // onError
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
      // onDone
      (evt) => {
        setMessages(prev => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last && last.role === 'agent' && last.loading) {
            copy[copy.length - 1] = {
              ...last, loading: false,
              toolCalls: [...toolCalls],
              toolResults: { ...toolResults },
              routingAgent: currentRouting,
            }
          }
          return copy
        })
        setSending(false)
        // Update convId from response
        if (evt.conversation_id && !currentConvId) {
          setCurrentConvId(evt.conversation_id)
        }
        // Reload from backend to get persisted messages
        const finalConvId = evt.conversation_id || convId
        if (finalConvId) {
          loadMessages(finalConvId)
          loadConversations()
        }
      }
    )
  }, [inputText, sending, currentConvId, sessionId, loadMessages, loadConversations])

  return (
    <div style={{ height: '100vh', display: 'flex', background: '#f5f5f5' }}>
      {/* Left sidebar - Conversations */}
      <div style={{
        width: 240, borderRight: '1px solid #e5e7eb', background: '#fff',
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid #f0f0f0',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <Text strong style={{ fontSize: 14 }}>Conversations</Text>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleNewConversation}>
            New
          </Button>
        </div>

        {/* Sub-Agents bar */}
        <div style={{
          padding: '8px 12px', borderBottom: '1px solid #f0f0f0',
          background: '#f8fafc',
        }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Registered Agents ({agents.length})
          </Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {agents.map(a => (
              <Tag key={a.id} color={getAgentColor(a.name)} style={{ fontSize: 11, margin: 0 }}>
                {a.name}
              </Tag>
            ))}
            {agents.length === 0 && (
              <Text type="secondary" style={{ fontSize: 11 }}>No agents yet</Text>
            )}
          </div>
        </div>

        {/* Conversation list */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>No conversations yet</Text>
            </div>
          ) : (
            conversations.map(c => (
              <div
                key={c.id}
                onClick={() => loadMessages(c.id)}
                style={{
                  padding: '8px 12px', cursor: 'pointer',
                  borderLeft: currentConvId === c.id ? '3px solid #10b981' : '3px solid transparent',
                  background: currentConvId === c.id ? '#f0fdf4' : 'transparent',
                  borderBottom: '1px solid #f0f0f0',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    fontWeight: currentConvId === c.id ? 600 : 400, fontSize: 13,
                  }}>
                    {c.title}
                  </div>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                    {c.message_count || 0} msgs
                  </div>
                </div>
                <DeleteOutlined
                  style={{ color: '#d1d5db', fontSize: 12, cursor: 'pointer', flexShrink: 0 }}
                  onClick={(e) => { e.stopPropagation(); handleDeleteConv(c.id) }}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{
          padding: '10px 20px', borderBottom: '1px solid #e5e7eb',
          background: '#fff', display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <RobotOutlined style={{ color: '#10b981', fontSize: 18 }} />
          <Text strong style={{ fontSize: 15 }}>Multi-Agent Chat</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            ({agents.length} agents available)
          </Text>
        </div>

        {/* Messages */}
        <div style={{
          flex: 1, overflow: 'auto', padding: '20px 28px',
          background: '#fafbfc',
        }}>
          {convLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          ) : messages.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <Empty
                image={<ApiOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
                description="Start a conversation with the Host Agent"
              >
                {agents.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 12 }}>Add agents on the Agents page first</Text>
                )}
              </Empty>
            </div>
          ) : (
            messages.map(m => (m.content || m.loading) ? <MessageBubble key={m.id} msg={m} /> : null)
          )}

          {sending && !messages.some(m => m.role === 'agent' && m.loading) && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
              <div style={{
                padding: '12px 16px', borderRadius: '16px 16px 16px 4px',
                background: '#fff', border: '1px solid #e5e7eb',
                boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <SyncOutlined spin style={{ color: '#6366f1' }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>Host Agent thinking...</Text>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{
          borderTop: '1px solid #e5e7eb', padding: 12,
          background: '#fff',
        }}>
          <div style={{ display: 'flex', gap: 8, maxWidth: 800, margin: '0 auto' }}>
            <TextArea
              rows={1}
              placeholder="Ask anything — Host Agent will delegate to the best sub-agent..."
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); handleSend() } }}
              disabled={sending || agents.length === 0}
              style={{ borderRadius: 12, paddingLeft: 16, paddingRight: 16 }}
            />
            <Button
              type="primary" icon={<SendOutlined />}
              shape="circle" size="large"
              onClick={handleSend}
              disabled={sending || !inputText.trim() || agents.length === 0}
              style={{ width: 44, height: 44 }}
            />
          </div>
        </div>
      </div>

      <EventsDrawer conversationId={currentConvId} />
    </div>
  )
}
