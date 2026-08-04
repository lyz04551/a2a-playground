import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Drawer, Input, Select, message } from 'antd'
import { MenuOutlined, SendOutlined, StopOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import * as api from '../api/api'
import useRunStream from '../hooks/useRunStream'
import ConversationSidebar from '../components/workspace/ConversationSidebar'
import ModeSwitch from '../components/workspace/ModeSwitch'
import MessageTimeline from '../components/workspace/MessageTimeline'
import RunTracePanel from '../components/workspace/RunTracePanel'
import PromptTemplates from '../components/PromptTemplates'
import DebugDrawer from '../components/workspace/DebugDrawer'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'
import { getWorkspaceSendState } from '../components/workspace/workspaceState'

export default function WorkspacePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const handledQuery = useRef(false)
  const query = new URLSearchParams(location.search)
  const initialAgentId = query.get('agent') || ''
  const initialMode = query.get('mode') || (initialAgentId ? 'direct' : 'auto')
  const workspace = useRunStream({ initialMode, initialAgentId })
  const { settings } = useConsoleSettings()
  const language = settings.language
  const zh = language === 'zh-CN'
  const [agents, setAgents] = useState([])
  const [conversations, setConversations] = useState([])
  const [modelConfigured, setModelConfigured] = useState(false)
  const [draft, setDraft] = useState('')
  const [drawer, setDrawer] = useState('')

  const refresh = async () => {
    const [listed, health, status, saved] = await Promise.all([
      api.listAgents(),
      api.checkAgentsHealth().catch(() => ({})),
      api.getSystemStatus().catch(() => ({ model: { configured: false } })),
      api.listConversations(),
    ])
    setAgents(listed.map(agent => ({ ...agent, online: Boolean(health[agent.id]?.online) })))
    setModelConfigured(Boolean(status.model?.configured))
    setConversations(saved)
  }

  useEffect(() => { refresh().catch(() => {}) }, [])
  useEffect(() => {
    if (handledQuery.current) return
    handledQuery.current = true
    const conversation = query.get('conversation')
    const prompt = query.get('prompt')
    const isNew = query.get('new') === '1'
    if (isNew) workspace.beginNewConversation(initialMode, initialAgentId)
    if (conversation) workspace.restoreConversation(conversation)
    if (prompt) setDraft(prompt)
    if (conversation || prompt || isNew) {
      const clean = new URLSearchParams(location.search)
      clean.delete('conversation'); clean.delete('prompt'); clean.delete('new')
      navigate(`/workspace${clean.toString() ? `?${clean}` : ''}`, { replace: true })
    }
  }, [initialAgentId, initialMode, location.search, navigate, query, workspace])
  useEffect(() => {
    if (!workspace.loading && workspace.conversationId) refresh().catch(() => {})
  }, [workspace.loading, workspace.conversationId])

  const sendState = getWorkspaceSendState({ mode: workspace.mode, selectedAgentId: workspace.selectedAgentId, agents, modelConfigured })
  const trace = useMemo(() => ({ ...workspace.state.run, tasks: workspace.state.taskOrder.map(id => workspace.state.tasksById[id]), approvals: workspace.state.approvals, artifacts: workspace.state.artifacts, rawEvents: workspace.state.rawEvents || [] }), [workspace.state])
  const changeMode = mode => {
    if (workspace.state.messages.length > 0) workspace.beginNewConversation(mode, mode === 'direct' ? workspace.selectedAgentId : '')
    else workspace.setMode(mode)
  }
  const submit = () => {
    if (!sendState.disabled && draft.trim()) { workspace.send(draft); setDraft('') }
  }
  const deleteConversation = async id => {
    try {
      await api.deleteConversation(id)
      if (workspace.conversationId === id) workspace.beginNewConversation()
      await refresh()
      message.success(zh ? '会话已删除' : 'Conversation deleted')
    } catch (cause) { message.error(cause.message || (zh ? '无法删除会话' : 'Unable to delete conversation')) }
  }
  const renameConversation = async (id, title) => {
    try {
      await api.updateConversation(id, title)
      await refresh()
      message.success(zh ? '会话已重命名' : 'Conversation renamed')
    } catch (cause) { message.error(cause.message || (zh ? '无法重命名会话' : 'Unable to rename conversation')); throw cause }
  }

  const sidebar = <ConversationSidebar conversations={conversations} activeId={workspace.conversationId} language={language} onSelect={id => { workspace.restoreConversation(id); setDrawer('') }} onNew={() => { workspace.beginNewConversation(); setDrawer('') }} onDelete={deleteConversation} onRename={renameConversation} />
  const tracePanel = <RunTracePanel run={trace} loading={workspace.loading} error={workspace.error} onDebug={() => setDrawer('debug')} onApproval={async (approval, decision) => { await api.decideApproval(approval.id, decision); workspace.restoreConversation(workspace.conversationId) }} />

  return <div className="agent-workspace">
    <div className="agent-workspace__desktop">{sidebar}</div>
    <main className="agent-workspace__main">
      <header className="agent-workspace__header"><Button className="agent-workspace__drawer-button" icon={<MenuOutlined />} onClick={() => setDrawer('conversations')}>{zh ? '会话' : 'Conversations'}</Button><div><span className="workspace-eyebrow">Unified Agent Workspace</span><h1>{workspace.mode === 'direct' ? (zh ? 'Direct 对话' : 'Direct conversation') : (zh ? '自动编排' : 'Auto orchestration')}</h1></div><Button className="agent-workspace__drawer-button" onClick={() => setDrawer('trace')}>{zh ? '轨迹' : 'Trace'}</Button></header>
      <section className="agent-workspace__controls"><ModeSwitch mode={workspace.mode} messageCount={workspace.state.messages.length} onChange={changeMode} language={language} />{workspace.mode === 'direct' ? <Select aria-label="Target Agent" placeholder={zh ? '选择在线 Agent' : 'Select an online Agent'} value={workspace.selectedAgentId || undefined} onChange={workspace.setSelectedAgentId} options={agents.filter(agent => agent.online).map(agent => ({ value: agent.id, label: agent.name }))} /> : <p><strong>Host Agent</strong> {zh ? `将协调 ${agents.filter(agent => agent.online).length} 个在线 Agent。` : `coordinates ${agents.filter(agent => agent.online).length} online Agents.`}</p>}</section>
      <section className="agent-workspace__messages"><MessageTimeline messages={workspace.state.messages} loading={workspace.loading} error={workspace.error} onRetry={workspace.retry} language={language} /></section>
      <footer className="agent-workspace__composer"><div className="agent-workspace__composer-main">{workspace.state.messages.length === 0 && <PromptTemplates language={language} compact onSelect={template => setDraft(template.prompt)} />}<Input.TextArea value={draft} onChange={event => setDraft(event.target.value)} onPressEnter={event => { if (!event.shiftKey) { event.preventDefault(); submit() } }} placeholder={sendState.reason || (zh ? '描述一个目标…' : 'Describe a goal…')} autoSize={{ minRows: 2, maxRows: 6 }} disabled={workspace.loading} /></div><Button type="primary" icon={workspace.loading ? <StopOutlined /> : <SendOutlined />} onClick={workspace.loading ? workspace.cancel : submit} disabled={!workspace.loading && (sendState.disabled || !draft.trim())}>{workspace.loading ? (zh ? '停止' : 'Stop') : (zh ? '发送' : 'Send')}</Button></footer>
    </main>
    <div className="agent-workspace__desktop agent-workspace__trace">{tracePanel}</div>
    <Drawer title={zh ? '会话' : 'Conversations'} open={drawer === 'conversations'} onClose={() => setDrawer('')} placement="left">{sidebar}</Drawer>
    <Drawer title={zh ? '运行轨迹' : 'Run trace'} open={drawer === 'trace'} onClose={() => setDrawer('')} placement="right">{tracePanel}</Drawer>
    <DebugDrawer open={drawer === 'debug'} onClose={() => setDrawer('')} run={trace} events={trace.rawEvents} language={language} />
  </div>
}
