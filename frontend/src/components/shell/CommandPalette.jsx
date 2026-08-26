import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Empty, Input, Modal, Spin, Tag } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  MessageOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import * as api from '../../api/api'
import { useConsoleSettings } from '../../context/ConsoleSettingsContext'
import { searchCommands } from '../../state/commandSearch'

const ICONS = {
  page: <DashboardOutlined />,
  agent: <RobotOutlined />,
  conversation: <MessageOutlined />,
  event: <FileTextOutlined />,
  action: <PlusOutlined />,
}

function staticCommands(zh) {
  return [
    { id: 'page-dashboard', type: 'page', title: zh ? '运行总览' : 'Dashboard', subtitle: '/dashboard', path: '/dashboard', keywords: ['overview', '首页'] },
    { id: 'page-workspace', type: 'page', title: zh ? 'Agent 工作台' : 'Agent Workspace', subtitle: '/workspace', path: '/workspace', keywords: ['chat', '对话'] },
    { id: 'page-agents', type: 'page', title: 'Agents', subtitle: '/agents', path: '/agents', keywords: ['智能体'] },
    { id: 'page-events', type: 'page', title: zh ? '执行事件' : 'Events', subtitle: '/events', path: '/events', keywords: ['日志', 'event'] },
    { id: 'action-new', type: 'action', title: zh ? '新建会话' : 'New conversation', subtitle: zh ? '打开自动编排工作台' : 'Open auto orchestration', path: '/workspace?mode=auto&new=1', keywords: ['new', 'chat'] },
  ]
}

export default function CommandPalette({ open, onClose }) {
  const navigate = useNavigate()
  const { settings } = useConsoleSettings()
  const [query, setQuery] = useState('')
  const [remoteCommands, setRemoteCommands] = useState([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState([])
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef(null)
  const zh = settings.language === 'zh-CN'

  useEffect(() => {
    if (!open) return undefined
    setQuery('')
    setActiveIndex(0)
    setLoading(true)
    const sources = [
      ['agents', api.listAgents()],
      ['conversations', api.listConversations()],
      ['events', api.listEvents()],
    ]
    let active = true
    Promise.allSettled(sources.map(([, request]) => request)).then(results => {
      if (!active) return
      const next = []
      const failures = []
      results.forEach((result, index) => {
        const name = sources[index][0]
        if (result.status === 'rejected') { failures.push(name); return }
        if (name === 'agents') result.value.forEach(agent => next.push({
          id: `agent-${agent.id}`, type: 'agent', title: agent.name, subtitle: agent.description || agent.url || agent.address,
          path: `/workspace?mode=direct&agent=${encodeURIComponent(agent.id)}`,
          keywords: [agent.id, ...(agent.skills || []).flatMap(skill => [skill.name, ...(skill.tags || [])])],
        }))
        if (name === 'conversations') result.value.forEach(conversation => next.push({
          id: `conversation-${conversation.id}`, type: 'conversation', title: conversation.title || (zh ? '未命名会话' : 'Untitled conversation'),
          subtitle: conversation.type === 'single' ? 'Direct' : 'Auto', path: `/workspace?conversation=${encodeURIComponent(conversation.id)}`,
          keywords: [conversation.id, conversation.agent_id],
        }))
        if (name === 'events') result.value.slice(0, 100).forEach(event => next.push({
          id: `event-${event.id || event.sequence || `${event.conversation_id}-${event.created_at}`}`, type: 'event',
          title: event.summary || event.type || (zh ? '执行事件' : 'Run event'), subtitle: event.conversation_title || event.agent_name || event.task_id,
          path: '/events', keywords: [event.conversation_id, event.task_id, event.tool_name, event.state],
        }))
      })
      setRemoteCommands(next)
      setFailed(failures)
      setLoading(false)
    })
    return () => { active = false }
  }, [open, zh])

  const results = useMemo(
    () => searchCommands([...staticCommands(zh), ...remoteCommands], query, { limit: 14 }),
    [query, remoteCommands, zh],
  )

  useEffect(() => setActiveIndex(0), [query])

  const execute = command => {
    if (!command) return
    navigate(command.path)
    onClose()
  }

  const onKeyDown = event => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActiveIndex(index => Math.min(index + 1, results.length - 1)) }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActiveIndex(index => Math.max(index - 1, 0)) }
    if (event.key === 'Enter') { event.preventDefault(); execute(results[activeIndex]) }
  }

  return (
    <Modal
      className="command-palette"
      width={650}
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      destroyOnHidden
      afterOpenChange={visible => visible && inputRef.current?.focus()}
    >
      <Input
        ref={inputRef}
        className="command-palette__input"
        variant="borderless"
        prefix={<SearchOutlined />}
        placeholder={zh ? '搜索页面、Agent、会话和事件…' : 'Search pages, Agents, conversations, and events…'}
        value={query}
        onChange={event => setQuery(event.target.value)}
        onKeyDown={onKeyDown}
        aria-label={zh ? '命令搜索' : 'Command search'}
        role="combobox"
        aria-expanded="true"
        aria-controls="command-results"
      />
      {failed.length > 0 && <Alert banner type="warning" showIcon message={`${zh ? '部分搜索源不可用' : 'Some search sources are unavailable'}: ${failed.join(', ')}`} />}
      <div className="command-palette__results" id="command-results" role="listbox">
        {loading && remoteCommands.length === 0 ? <div className="command-palette__loading"><Spin size="small" /> {zh ? '正在加载工作区数据…' : 'Loading workspace data…'}</div> : results.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={zh ? '没有匹配结果' : 'No matching commands'} /> : results.map((command, index) => (
          <button
            type="button"
            key={command.id}
            className={index === activeIndex ? 'is-active' : ''}
            role="option"
            aria-selected={index === activeIndex}
            onMouseEnter={() => setActiveIndex(index)}
            onClick={() => execute(command)}
          >
            <span className="command-palette__icon">{ICONS[command.type]}</span>
            <span><strong>{command.title}</strong><small>{command.subtitle}</small></span>
            <Tag variant="filled">{command.type}</Tag>
          </button>
        ))}
      </div>
      <footer><span><kbd>↑↓</kbd> {zh ? '选择' : 'Select'}</span><span><kbd>↵</kbd> {zh ? '打开' : 'Open'}</span><span><kbd>esc</kbd> {zh ? '关闭' : 'Close'}</span></footer>
    </Modal>
  )
}
