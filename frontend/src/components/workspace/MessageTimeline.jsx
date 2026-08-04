import React from 'react'
import { InboxOutlined, LoadingOutlined, ReloadOutlined } from '@ant-design/icons'
import ToolActivity from './ToolActivity'
import MessageActions from './MessageActions'

export default function MessageTimeline({ messages = [], loading = false, error, onRetry, onArtifactOpen, language = 'zh-CN' }) {
  const zh = language === 'zh-CN'
  if (loading && messages.length === 0) return <div className="workspace-state" role="status"><LoadingOutlined /> {zh ? '正在加载会话…' : 'Loading conversation…'}</div>
  if (error) return <div className="workspace-state workspace-state--error" role="alert">{error}<button type="button" onClick={onRetry}><ReloadOutlined /> {zh ? '重试' : 'Retry'}</button></div>
  if (messages.length === 0) return <div className="workspace-state"><InboxOutlined /><span>{zh ? '还没有消息。描述一个目标即可开始运行。' : 'No messages yet. Describe a goal to start a run.'}</span></div>

  return (
    <ol className="workspace-timeline" aria-label="Conversation messages">
      {messages.map(message => (
        <li className={`workspace-message workspace-message--${message.role || 'agent'}`} key={message.id}>
          <header><strong>{message.agentName || (message.role === 'user' ? (zh ? '你' : 'You') : 'Agent')}</strong><span>{message.status && <small>{message.status}</small>}<MessageActions content={message.content} language={language} /></span></header>
          <div className="workspace-message__body">{message.content}</div>
          {message.toolCalls?.map(tool => <ToolActivity key={tool.id || tool.tool} tool={tool.tool} status={tool.status} input={tool.arguments || tool.args} output={tool.output || message.toolResults?.[tool.id]} error={tool.error} duration={tool.duration} />)}
          {message.artifacts?.map(artifact => <button className="workspace-artifact" type="button" key={artifact.id} onClick={() => onArtifactOpen?.(artifact)}>Artifact: {artifact.name || artifact.id}</button>)}
        </li>
      ))}
      {loading && <li className="workspace-state" role="status"><LoadingOutlined /> {zh ? 'Agent 正在响应…' : 'Agent is responding…'}</li>}
    </ol>
  )
}
