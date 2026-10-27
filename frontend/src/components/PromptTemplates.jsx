import React from 'react'
import { RobotOutlined } from '@ant-design/icons'
import { agentPromptTemplates } from '../data/promptTemplates'

export default function PromptTemplates({ agents = [], language = 'en-US', compact = false, onSelect }) {
  const templates = agentPromptTemplates(agents, language)
  if (!templates.length) return null
  return (
    <div className={`prompt-templates ${compact ? 'prompt-templates--compact' : ''}`}>
      {templates.map(template => (
        <button type="button" key={template.id} onClick={() => onSelect?.(template)}>
          <span className="prompt-template__icon"><RobotOutlined /></span>
          <span>
            <strong>{template.title}</strong>
            {!compact && <small>{template.prompt}</small>}
          </span>
        </button>
      ))}
    </div>
  )
}
