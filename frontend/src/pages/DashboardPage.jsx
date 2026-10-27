import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Empty, Skeleton, Tag } from 'antd'
import {
  CheckCircleFilled,
  ClockCircleOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import * as api from '../api/api'
import OnboardingPanel from '../components/OnboardingPanel'
import PromptTemplates from '../components/PromptTemplates'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'
import { deriveOnboardingSteps, summarizeDashboard } from '../state/dashboardState'

const EMPTY_DATA = { agents: [], conversations: [], runs: [], approvals: [], status: { model: { configured: false } } }

export default function DashboardPage() {
  const navigate = useNavigate()
  const { settings, updateSettings } = useConsoleSettings()
  const [data, setData] = useState(EMPTY_DATA)
  const [loading, setLoading] = useState(true)
  const [degraded, setDegraded] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    const requests = [
      ['agents', api.listAgents()],
      ['health', api.checkAgentsHealth()],
      ['status', api.getSystemStatus()],
      ['conversations', api.listConversations()],
      ['runs', api.listRuns()],
      ['approvals', api.listApprovals()],
    ]
    const results = await Promise.allSettled(requests.map(([, request]) => request))
    const values = {}
    const failed = []
    results.forEach((result, index) => {
      const key = requests[index][0]
      if (result.status === 'fulfilled') values[key] = result.value
      else failed.push(key)
    })
    const agents = (values.agents || []).map(agent => ({ ...agent, online: Boolean(values.health?.[agent.id]?.online) }))
    setData(current => ({
      agents: values.agents ? agents : current.agents,
      status: values.status || current.status,
      conversations: values.conversations || current.conversations,
      runs: values.runs || current.runs,
      approvals: values.approvals || current.approvals,
    }))
    setDegraded(failed)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const summary = useMemo(() => summarizeDashboard(data), [data])
  const onboarding = useMemo(() => deriveOnboardingSteps({
    modelConfigured: Boolean(data.status?.model?.configured),
    agents: data.agents,
    conversations: data.conversations,
  }), [data])
  const recentRuns = data.runs.slice(0, 5)
  const language = settings.language
  const zh = language === 'zh-CN'

  return (
    <div className="console-page dashboard-page">
      <div className="console-page__inner">
        <header className="console-page-header">
          <div><span className="console-eyebrow">A2A Operations</span><h1>{zh ? '运行总览' : 'Operations overview'}</h1><p>{zh ? '集中查看 Agent 状态、执行任务与待审批操作。' : 'Monitor Agents, runs, and approval work from one place.'}</p></div>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>{zh ? '刷新' : 'Refresh'}</Button>
        </header>

        {degraded.length > 0 && <Alert className="dashboard-degraded" type="warning" showIcon message={zh ? '部分数据暂不可用' : 'Some data is unavailable'} description={degraded.join(', ')} action={<Button size="small" onClick={load}>{zh ? '重试' : 'Retry'}</Button>} />}

        {loading && data.agents.length === 0 ? <Skeleton active paragraph={{ rows: 8 }} /> : <>
          <section className="dashboard-metrics" aria-label="System metrics">
            {[
              [zh ? '在线 Agent' : 'Online Agents', summary.onlineAgents, `/ ${summary.agents}`, <RobotOutlined />, 'primary'],
              [zh ? '近期任务' : 'Recent runs', summary.runs, '', <NodeIndexOutlined />, 'blue'],
              [zh ? '已完成' : 'Completed', summary.completedRuns, '', <CheckCircleFilled />, 'green'],
              [zh ? '等待审批' : 'Pending approvals', summary.pendingApprovals, '', <SafetyCertificateOutlined />, 'amber'],
            ].map(([label, value, suffix, icon, tone]) => <article className={`dashboard-metric console-card tone-${tone}`} key={label}><div>{icon}</div><span>{label}</span><strong>{value}<small>{suffix}</small></strong></article>)}
          </section>

          {!settings.onboardingComplete && !onboarding.every(step => step.complete) && <OnboardingPanel steps={onboarding} language={language} onDismiss={() => updateSettings({ onboardingComplete: true })} />}

          <div className="dashboard-grid">
            <section className="dashboard-section console-card">
              <header><div><span className="console-eyebrow">Quick start</span><h2>{zh ? '快捷任务' : 'Prompt templates'}</h2></div><Tag color="green">Kubernetes</Tag></header>
              <PromptTemplates language={language} onSelect={template => navigate(`/workspace?mode=auto&prompt=${encodeURIComponent(template.prompt)}`)} />
            </section>
            <section className="dashboard-section dashboard-runs console-card">
              <header><div><span className="console-eyebrow">Recent activity</span><h2>{zh ? '最近任务' : 'Recent runs'}</h2></div><Button type="link" onClick={() => navigate('/events')}>{zh ? '查看全部' : 'View all'}</Button></header>
              {recentRuns.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={zh ? '暂无运行记录' : 'No runs yet'} /> : <div className="dashboard-run-list">{recentRuns.map(run => <button type="button" key={run.id || run.run_id} onClick={() => navigate('/events')}><span className={`dashboard-run-dot is-${run.status || 'unknown'}`} /><span><strong>{run.title || run.goal || run.id || run.run_id}</strong><small><ClockCircleOutlined /> {run.status || 'unknown'}</small></span></button>)}</div>}
            </section>
          </div>
        </>}
      </div>
    </div>
  )
}
