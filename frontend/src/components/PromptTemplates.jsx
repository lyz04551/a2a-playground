import React from 'react'
import {
  BugOutlined,
  DeploymentUnitOutlined,
  HeartOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { PROMPT_TEMPLATES } from '../data/promptTemplates'

const ICONS = {
  pulse: <HeartOutlined />,
  bug: <BugOutlined />,
  shield: <SafetyCertificateOutlined />,
  event: <WarningOutlined />,
  deploy: <DeploymentUnitOutlined />,
}

export default function PromptTemplates({ language = 'zh-CN', compact = false, onSelect }) {
  return (
    <div className={`prompt-templates ${compact ? 'prompt-templates--compact' : ''}`}>
      {PROMPT_TEMPLATES.map(template => (
        <button type="button" key={template.id} onClick={() => onSelect?.(template)}>
          <span className="prompt-template__icon">{ICONS[template.icon]}</span>
          <span>
            <strong>{template.title[language]}</strong>
            {!compact && <small>{template.description[language]}</small>}
          </span>
        </button>
      ))}
    </div>
  )
}
