import React from 'react'
import { InboxOutlined, LoadingOutlined, ReloadOutlined } from '@ant-design/icons'
import ToolActivity from './ToolActivity'
import MessageActions from './MessageActions'
import { formatAgentOutput } from './agentOutput'
import MarkdownContent from '../MarkdownContent'
import { recentAgentActivity } from './agentActivity'

export default function MessageTimeline({ messages = [], tasks = [], thinking = '', loading = false, stage, error, onRetry, onArtifactOpen, language = 'zh-CN' }) {
  const zh = language === 'zh-CN'
  const activity = loading ? recentAgentActivity(tasks) : []
  if (loading && messages.length === 0) return <div className="workspace-state" role="status"><LoadingOutlined /> {zh ? '正在加载会话…' : 'Loading conversation…'}</div>
  if (error) return <div className="workspace-state workspace-state--error" role="alert">{error}<button type="button" onClick={onRetry}><ReloadOutlined /> {zh ? '重试' : 'Retry'}</button></div>
  if (messages.length === 0) return <div className="workspace-state"><InboxOutlined /><span>{zh ? '还没有消息。描述一个目标即可开始运行。' : 'No messages yet. Describe a goal to start a run.'}</span></div>

  return (
    <ol className="workspace-timeline" aria-label="Conversation messages">
      {messages.map(message => (
        <li className={`workspace-message workspace-message--${message.role || 'agent'}`} key={message.id}>
          <header><strong>{message.agentName || (message.role === 'user' ? (zh ? '你' : 'You') : 'Agent')}</strong><span>{message.status && <small>{message.status}</small>}<MessageActions content={message.role === 'user' ? message.content : formatAgentOutput(message.content)} language={language} /></span></header>
          <div className="workspace-message__body">{message.role === 'user' ? message.content : <MarkdownContent>{formatAgentOutput(message.content)}</MarkdownContent>}</div>
          {message.toolCalls?.map(tool => <ToolActivity key={tool.id || tool.tool} tool={tool.tool} status={tool.status} input={tool.arguments || tool.args} output={tool.output || message.toolResults?.[tool.id]} error={tool.error} duration={tool.duration} />)}
          {message.artifacts?.map(artifact => <button className="workspace-artifact" type="button" key={artifact.id} onClick={() => onArtifactOpen?.(artifact)}>Artifact: {artifact.name || artifact.id}</button>)}
        </li>
      ))}
      {loading && <li className="workspace-live">
        <div className="workspace-live__header">
          <span className="workspace-live__pulse" aria-hidden="true"><span /></span>
          <div className="workspace-live__heading" role="status" aria-live="polite">
            <span className="workspace-live__eyebrow">{zh ? '正在执行' : 'IN PROGRESS'}</span>
            <strong>{(zh ? stage?.textZh : stage?.textEn) || (zh ? 'Agent 正在响应…' : 'Agent is responding…')}</strong>
          </div>
          <span className="workspace-live__state">{zh ? '实时更新' : 'Live'}</span>
        </div>
        {stage?.active?.length > 0 && <div className="workspace-live__agents">{stage.active.map(item => <span key={item.id}>{item.agentName}{item.objective ? ` · ${item.objective}` : ''}</span>)}</div>}
        {(thinking || activity.length > 0) && <div className="workspace-live__details">
          {thinking && <section className="workspace-live__thinking" aria-live="off" aria-label={zh ? '模型实时分析' : 'Live model analysis'}>
            <div className="workspace-live__section-title"><span className="workspace-live__section-mark" />{zh ? '实时分析' : 'Live analysis'}<small>{zh ? '生成中' : 'Generating'}</small></div>
            <p>{thinking}</p>
          </section>}
          {activity.length > 0 && <section className="workspace-live__tools" aria-label={zh ? '最近工具调用' : 'Recent tool calls'}>
            <div className="workspace-live__section-title">{zh ? '最近工具调用' : 'Recent tool calls'}<small>{zh ? '详细记录见右侧运行轨迹' : 'Details in run trace'}</small></div>
            <ol>{activity.map(item => <li key={item.id} className={`is-${item.status}`}><span className="workspace-live__tool-number">{String(item.number).padStart(2, '0')}</span><code title={item.name}>{item.name}</code><em>{item.status === 'working' ? (zh ? '执行中' : 'Running') : item.status === 'completed' ? (zh ? '已完成' : 'Done') : (zh ? '未完成' : 'Incomplete')}</em></li>)}</ol>
          </section>}
        </div>}
        {!thinking && activity.length === 0 && <p className="workspace-live__waiting">{zh ? '正在准备下一步，新的分析和工具活动会显示在这里。' : 'Preparing the next step. Analysis and tool activity will appear here.'}</p>}
      </li>}
    </ol>
  )
}
