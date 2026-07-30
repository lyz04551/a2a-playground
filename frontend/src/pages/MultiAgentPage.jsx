import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { Button, Empty, Input, Spin, Tooltip } from 'antd'
import {
  BranchesOutlined,
  DeleteOutlined,
  MenuFoldOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
} from '@ant-design/icons'
import * as api from '../api/api'
import AgentBadge from '../components/AgentBadge'
import OrchestrationTrace from '../components/OrchestrationTrace'
import { emptyRunState, reduceRunEvent } from '../state/runEvents'

const { TextArea } = Input

function Message({ message }) {
  const user = message.role === 'user'
  const agent = message.routingAgent || message.metadata?.routing_agent || 'Host Agent'
  return (
    <article className={`run-message ${user ? 'run-message--user' : ''}`}>
      {!user && <AgentBadge agentId={agent} />}
      <div className="run-message__bubble">
        {message.toolCalls?.length > 0 && (
          <div className="run-message__tools">
            {message.toolCalls.map(call => (
              <details key={call.id}>
                <summary>{call.tool}</summary>
                <pre>{JSON.stringify(call.args || {}, null, 2)}</pre>
                {message.toolResults?.[call.id] && (
                  <pre>{String(message.toolResults[call.id]).slice(0, 800)}</pre>
                )}
              </details>
            ))}
          </div>
        )}
        {message.content || (message.loading ? 'Host 正在规划下一步…' : '')}
      </div>
    </article>
  )
}

export default function MultiAgentPage() {
  const endRef = useRef(null)
  const [agents, setAgents] = useState([])
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [currentConvId, setCurrentConvId] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [traceOpen, setTraceOpen] = useState(false)
  const [run, dispatch] = useReducer(reduceRunEvent, emptyRunState)

  const loadConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversationsByType('multi'))
    } catch {}
  }, [])

  useEffect(() => {
    api.hostAgents().then(setAgents).catch(() => {})
    loadConversations()
  }, [loadConversations])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadConversation = useCallback(async id => {
    setLoading(true)
    try {
      const conversation = await api.getConversation(id)
      const loadedMessages = conversation?.messages || []
      setMessages(loadedMessages)
      setCurrentConvId(id)
      const lastSession = [...loadedMessages].reverse().find(item => item.task_id)?.task_id
      if (lastSession) {
        setSessionId(lastSession)
        const savedRun = await api.getRun(lastSession).catch(() => null)
        savedRun?.approvals?.forEach(approval => {
          dispatch({ type: 'approval_required', approval })
        })
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const createConversation = useCallback(async () => {
    const conversation = await api.createConversation(
      'multi-host',
      'New orchestration',
      'multi',
    )
    setCurrentConvId(conversation.id)
    setMessages([])
    setSessionId('')
    loadConversations()
  }, [loadConversations])

  const deleteConversation = useCallback(async id => {
    await api.deleteConversation(id)
    if (id === currentConvId) {
      setCurrentConvId('')
      setMessages([])
      setSessionId('')
    }
    loadConversations()
  }, [currentConvId, loadConversations])

  const updateWorkingMessage = useCallback(updater => {
    setMessages(previous => {
      const copy = [...previous]
      const index = copy.findLastIndex(item => item.role === 'agent' && item.loading)
      if (index >= 0) copy[index] = updater(copy[index])
      return copy
    })
  }, [])

  const send = useCallback(async () => {
    const content = input.trim()
    if (!content || sending) return
    setSending(true)
    setInput('')

    let conversationId = currentConvId
    if (!conversationId) {
      const conversation = await api.createConversation(
        'multi-host',
        content.slice(0, 44),
        'multi',
      )
      conversationId = conversation.id
      setCurrentConvId(conversationId)
    }
    const activeSession = sessionId || `run-${Date.now()}`
    setSessionId(activeSession)

    const userMessage = { id: `u-${Date.now()}`, role: 'user', content }
    const hostMessage = {
      id: `h-${Date.now()}`,
      role: 'agent',
      content: '',
      routingAgent: 'Host Agent',
      loading: true,
      toolCalls: [],
      toolResults: {},
    }
    setMessages(previous => [...previous, userMessage, hostMessage])
    dispatch({ type: 'run_started' })
    const toolCalls = []
    const toolResults = {}
    let routingAgent = 'Host Agent'

    api.hostLgSendStream(
      content,
      activeSession,
      conversationId,
      event => {
        dispatch(event)
        updateWorkingMessage(message => ({
          ...message,
          content: message.content + (event.text || ''),
          routingAgent,
        }))
      },
      event => {
        toolCalls.push({ tool: event.tool, args: event.args, id: event.id })
        dispatch(event)
        updateWorkingMessage(message => ({
          ...message,
          toolCalls: [...toolCalls],
          toolResults: { ...toolResults },
        }))
      },
      event => {
        toolResults[event.id] = event.result
        dispatch(event)
        updateWorkingMessage(message => ({
          ...message,
          toolCalls: [...toolCalls],
          toolResults: { ...toolResults },
        }))
      },
      event => {
        routingAgent = event.agent || event.agent_id
        dispatch(event)
        updateWorkingMessage(message => ({ ...message, routingAgent }))
      },
      event => {
        dispatch(event)
        setTraceOpen(true)
      },
      error => {
        dispatch({ type: 'error' })
        updateWorkingMessage(message => ({
          ...message,
          loading: false,
          content: `执行失败：${error}`,
        }))
        setSending(false)
      },
      event => {
        dispatch({ ...event, type: 'done' })
        updateWorkingMessage(message => ({
          ...message,
          loading: false,
          routingAgent,
          toolCalls: [...toolCalls],
          toolResults: { ...toolResults },
        }))
        setSending(false)
        loadConversations()
      },
    )
  }, [
    currentConvId,
    input,
    loadConversations,
    sending,
    sessionId,
    updateWorkingMessage,
  ])

  const decideApproval = useCallback(async (approval, decision) => {
    const response = await api.decideApproval(approval.id, decision)
    dispatch({
      type: 'approval_decided',
      approvalId: approval.id,
      decision,
    })
    const resultText = response?.result?.text
    if (resultText) {
      setMessages(previous => [...previous, {
        id: `approval-${Date.now()}`,
        role: 'agent',
        routingAgent: 'Host Agent',
        content: resultText,
      }])
    }
    dispatch({ type: 'done' })
    loadConversations()
  }, [loadConversations])

  return (
    <div className="orchestration-shell">
      <nav className="run-sidebar">
        <div className="run-sidebar__heading">
          <div>
            <strong>多智能体会话</strong>
            <small>由 Host Agent 统一协调</small>
          </div>
          <span>{conversations.length}</span>
        </div>
        <Button
          className="new-run-button"
          icon={<PlusOutlined />}
          onClick={createConversation}
        >
          新建会话
        </Button>
        <div className="run-sidebar__agents">
          <span>Agent 网络 · {agents.length} 在线</span>
          <div>{agents.map(agent => <AgentBadge key={agent.id} agentId={agent.id} agentName={agent.name} compact />)}</div>
        </div>
        <div className="run-sidebar__list">
          {conversations.map(conversation => (
            <button
              key={conversation.id}
              className={conversation.id === currentConvId ? 'active' : ''}
              onClick={() => loadConversation(conversation.id)}
            >
              <BranchesOutlined />
              <span><strong>{conversation.title}</strong><small>{conversation.message_count || 0} 条消息</small></span>
              <DeleteOutlined onClick={event => {
                event.stopPropagation()
                deleteConversation(conversation.id)
              }} />
            </button>
          ))}
        </div>
      </nav>

      <main className="run-conversation">
        <header className="run-header">
          <div>
            <span className="run-header__eyebrow">Host Agent 主导的 A2A 协作</span>
            <h2>{sessionId ? `任务 ${sessionId.slice(-8)}` : '新的多智能体任务'}</h2>
          </div>
          <div className="run-header__actions">
            <span className="live-pill"><i /> 实时</span>
            <Tooltip title="查看执行轨迹">
              <Button
                className="trace-toggle"
                icon={<MenuFoldOutlined />}
                onClick={() => setTraceOpen(value => !value)}
              />
            </Tooltip>
          </div>
        </header>

        <section className="run-messages">
          {loading ? <Spin /> : messages.length === 0 ? (
            <Empty
              image={<RobotOutlined className="run-empty-icon" />}
              description="描述你的目标，Host 会决定何时追问、调用 Agent 或请求审批。"
            />
          ) : messages.map(message => (
            <Message key={message.id} message={message} />
          ))}
          <div ref={endRef} />
        </section>

        <footer className="run-composer">
          <TextArea
            autoSize={{ minRows: 1, maxRows: 5 }}
            value={input}
            onChange={event => setInput(event.target.value)}
            onPressEnter={event => {
              if (!event.shiftKey) {
                event.preventDefault()
                send()
              }
            }}
            placeholder="告诉 Host 你的目标，例如：诊断 payments 服务并给出修复方案…"
            disabled={sending || agents.length === 0}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={send}
            disabled={!input.trim() || sending || agents.length === 0}
          >
            发送
          </Button>
        </footer>
      </main>

      <div className={`trace-panel ${traceOpen ? 'trace-panel--open' : ''}`}>
        <OrchestrationTrace run={run} onApproval={decideApproval} />
      </div>
    </div>
  )
}
