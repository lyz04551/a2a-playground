import React from 'react'
import { canChangeMode } from './workspaceState'

const modes = [
  { id: 'direct', label: 'Direct', description: { 'zh-CN': '发送给一个指定 Agent', 'en-US': 'Send to one selected Agent' } },
  { id: 'auto', label: 'Auto', description: { 'zh-CN': '由 Host 自动协调任务', 'en-US': 'Host coordinates the work' } },
]

export default function ModeSwitch({ mode = 'auto', messageCount = 0, disabled = false, onChange, language = 'zh-CN' }) {
  const changeAllowed = canChangeMode({ messageCount })
  const unavailable = disabled || !changeAllowed

  return (
    <div className="workspace-mode-switch">
      <div className="workspace-mode-switch__control" role="group" aria-label={language === 'zh-CN' ? '执行模式' : 'Execution mode'}>
        {modes.map(option => (
          <button
            key={option.id}
            type="button"
            className={option.id === mode ? 'is-selected' : ''}
            aria-pressed={option.id === mode}
            disabled={unavailable}
            title={option.description[language]}
            onClick={() => onChange?.(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {!changeAllowed && <p className="workspace-hint">{language === 'zh-CN' ? '新建会话后可以切换模式。' : 'Start a new conversation to change mode.'}</p>}
    </div>
  )
}
