import React from 'react'
import { Button, Progress } from 'antd'
import { CheckCircleFilled, CloseOutlined, RightOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const LABELS = {
  'zh-CN': {
    title: '完成控制台初始化', description: '完成以下步骤后，即可开始可靠的多 Agent 编排。', dismiss: '暂时隐藏',
    model: '配置 Host 模型', registered: '注册至少一个 Agent', online: '确认 Agent 在线', conversation: '发起第一次会话',
  },
  'en-US': {
    title: 'Finish console setup', description: 'Complete these steps before running reliable multi-Agent orchestration.', dismiss: 'Hide for now',
    model: 'Configure the Host model', registered: 'Register an Agent', online: 'Bring an Agent online', conversation: 'Start the first conversation',
  },
}

export default function OnboardingPanel({ steps, language = 'zh-CN', onDismiss }) {
  const navigate = useNavigate()
  const copy = LABELS[language]
  const complete = steps.filter(step => step.complete).length
  const actions = { model: '/dashboard', registered: '/agents', online: '/agents', conversation: '/workspace' }

  return (
    <section className="onboarding-panel console-card">
      <header>
        <div><span className="console-eyebrow">Getting started</span><h2>{copy.title}</h2><p>{copy.description}</p></div>
        <Button type="text" aria-label={copy.dismiss} icon={<CloseOutlined />} onClick={onDismiss} />
      </header>
      <Progress percent={Math.round((complete / steps.length) * 100)} showInfo={false} strokeColor="#10b981" />
      <div className="onboarding-steps">
        {steps.map(step => (
          <button type="button" key={step.id} className={step.complete ? 'is-complete' : ''} onClick={() => navigate(actions[step.id])}>
            <CheckCircleFilled /><span>{copy[step.id]}</span><RightOutlined />
          </button>
        ))}
      </div>
    </section>
  )
}
