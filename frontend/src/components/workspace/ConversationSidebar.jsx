import React, { useMemo, useState } from 'react'
import { Button, Empty, Input, Popconfirm, Tooltip } from 'antd'
import { CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { filterConversations, normalizeConversationTitle } from '../../state/workspaceConversations'

export default function ConversationSidebar({ conversations = [], activeId, language = 'zh-CN', onSelect, onNew, onDelete, onRename }) {
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState('')
  const [title, setTitle] = useState('')
  const visible = useMemo(() => filterConversations(conversations, query), [conversations, query])
  const zh = language === 'zh-CN'

  const saveTitle = async id => {
    const nextTitle = normalizeConversationTitle(title)
    if (!nextTitle) return
    await onRename?.(id, nextTitle)
    setEditingId('')
  }

  return (
    <aside className="workspace-conversations">
      <header><div><span className="workspace-eyebrow">Workspace</span><h2>{zh ? '会话' : 'Conversations'}</h2></div><Button type="text" aria-label="New conversation" icon={<PlusOutlined />} onClick={onNew} /></header>
      <Button className="workspace-new-conversation" onClick={onNew} icon={<PlusOutlined />}>{zh ? '新建会话' : 'New conversation'}</Button>
      <Input allowClear size="small" className="workspace-conversation-search" prefix={<SearchOutlined />} placeholder={zh ? '搜索会话' : 'Search conversations'} value={query} onChange={event => setQuery(event.target.value)} />
      <nav aria-label={zh ? '会话列表' : 'Conversations'}>
        {visible.length ? visible.map(conversation => (
          <div className={`workspace-conversation-item ${conversation.id === activeId ? 'is-active' : ''}`} key={conversation.id}>
            {editingId === conversation.id ? <div className="workspace-conversation-edit"><Input size="small" autoFocus value={title} maxLength={80} onChange={event => setTitle(event.target.value)} onPressEnter={() => saveTitle(conversation.id)} /><button type="button" aria-label="Save title" onClick={() => saveTitle(conversation.id)}><CheckOutlined /></button><button type="button" aria-label="Cancel rename" onClick={() => setEditingId('')}><CloseOutlined /></button></div> : <button type="button" className="workspace-conversation-item__select" onClick={() => onSelect?.(conversation.id)}><strong>{conversation.title || (zh ? '未命名会话' : 'Untitled conversation')}</strong><small>{conversation.type === 'single' ? 'Direct' : 'Auto'}</small></button>}
            {editingId !== conversation.id && <div className="workspace-conversation-item__actions"><Tooltip title={zh ? '重命名' : 'Rename'}><button type="button" aria-label="Rename conversation" onClick={() => { setEditingId(conversation.id); setTitle(conversation.title || '') }}><EditOutlined /></button></Tooltip><Popconfirm title={zh ? '删除此会话？' : 'Delete this conversation?'} description={zh ? '会话中的消息也会被删除。' : 'Messages in this conversation will be removed.'} okText={zh ? '删除' : 'Delete'} cancelText={zh ? '取消' : 'Cancel'} onConfirm={() => onDelete?.(conversation.id)}><button type="button" className="workspace-conversation-item__delete" aria-label={`Delete ${conversation.title || 'conversation'}`}><DeleteOutlined /></button></Popconfirm></div>}
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query ? (zh ? '没有匹配的会话' : 'No matching conversations') : (zh ? '会话将在这里显示' : 'Your conversations will appear here')} />}
      </nav>
    </aside>
  )
}
