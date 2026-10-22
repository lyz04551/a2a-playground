import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Input, Tag } from 'antd'
import { ApiOutlined, CloudServerOutlined, RobotOutlined } from '@ant-design/icons'

import * as api from '../api/api'
import { diagnosticView } from '../state/connectionDiagnostics'

function ProbeResult({ title, subtitle, result, language, detail }) {
  const view = diagnosticView(result, language)
  return <article className="connection-test__probe">
    <div className="connection-test__probe-copy"><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</div>
    <div className="connection-test__probe-result">{detail && <small>{detail}</small>}{view.latency && <small>{view.latency}</small>}<Tag color={view.color}>{view.label}</Tag></div>
    {view.error && <code>{view.error}</code>}
  </article>
}

function DiagnosticCard({ icon, title, description, action, loading, error, children, empty, language, className = '', actionLabel }) {
  const zh = language === 'zh-CN'
  return <section className={`console-card connection-test ${className}`}>
    <header><div className="connection-test__heading"><span>{icon}</span><div><h2>{title}</h2><p>{description}</p></div></div><Button type="primary" loading={loading} onClick={action}>{actionLabel || (zh ? '开始测试' : 'Run test')}</Button></header>
    {error && <Alert type="error" showIcon message={error} />}
    {empty && !error ? <p className="connection-test__empty">{zh ? '尚未运行此项测试。' : 'This test has not been run.'}</p> : <div className="connection-test__results">{children}</div>}
  </section>
}

function ToolCatalog({ agent, language, index }) {
  const zh = language === 'zh-CN'
  const [query, setQuery] = useState('')
  const tools = agent.mcp?.tools || []
  const visible = tools.filter(tool => `${tool.name} ${tool.description}`.toLowerCase().includes(query.trim().toLowerCase()))
  const counts = tools.reduce((result, tool) => ({ ...result, [tool.access]: (result[tool.access] || 0) + 1 }), {})
  const labels = { allow: zh ? '可调用' : 'Callable', approval_required: zh ? '需审批' : 'Approval required', deny: zh ? '不可调用' : 'Unavailable' }
  const view = diagnosticView(agent.mcp || agent, language)
  const total = tools.length
  return <article className="connection-test__agent">
    <div className="connection-test__agent-top"><span className="connection-test__agent-index">{String(index + 1).padStart(2, '0')}</span><span className={`connection-test__agent-state is-${agent.mcp?.state || 'unknown'}`}><i />{view.label}</span></div>
    <h3>{agent.name || agent.id}</h3>
    <p className="connection-test__agent-meta">MCP Server{view.latency && <> <span aria-hidden="true">·</span> {view.latency}</>}</p>
    {view.error && <p className="connection-test__agent-error">{view.error}</p>}
    {agent.mcp?.state === 'ok' && <>
      <div className="connection-test__agent-total"><strong>{total}</strong><span>{zh ? '个已发现工具' : 'discovered tools'}</span></div>
      <div className="connection-test__access-stats">{['allow', 'approval_required', 'deny'].map(access => <div key={access} className={`is-${access}`}><strong>{counts[access] || 0}</strong><span>{labels[access]}</span></div>)}</div>
      <div className="connection-test__access-meter" aria-label={zh ? '工具权限分布' : 'Tool access distribution'}>{['allow', 'approval_required', 'deny'].map(access => <span key={access} className={`is-${access}`} style={{ flexGrow: counts[access] || 0 }} />)}</div>
    </>}
    {agent.mcp?.state === 'ok' && <details className="connection-test__catalog">
      <summary>{zh ? '浏览工具目录' : 'Browse tool catalog'} <span>{zh ? '按名称和说明搜索' : 'Search names and descriptions'}</span></summary>
      <Input.Search aria-label={zh ? '搜索工具' : 'Search tools'} placeholder={zh ? '搜索工具名称或说明' : 'Search tool names or descriptions'} value={query} onChange={event => setQuery(event.target.value)} allowClear />
      <ul className="connection-test__tool-list">{visible.map(tool => <li key={tool.name}><div><code>{tool.name}</code><span className={`connection-test__tool-access is-${tool.access}`}>{labels[tool.access] || tool.access}</span></div>{tool.description && <small>{tool.description}</small>}</li>)}</ul>
      {visible.length === 0 && <p className="connection-test__empty">{zh ? '没有匹配的工具。' : 'No matching tools.'}</p>}
    </details>}
  </article>
}

export default function ConnectionDiagnostics({ language = 'zh-CN' }) {
  const zh = language === 'zh-CN'
  const [results, setResults] = useState({ host: null, models: null, mcp: null })
  const [loading, setLoading] = useState({ host: false, models: false, mcp: false })
  const [errors, setErrors] = useState({ host: '', models: '', mcp: '' })
  const autoProbeStarted = useRef(false)
  const mcpAgents = results.mcp?.agents || []
  const connectedCount = mcpAgents.filter(agent => agent.mcp?.state === 'ok').length
  const uniqueTools = new Set(mcpAgents.flatMap(agent => (agent.mcp?.tools || []).map(tool => tool.name))).size

  const run = async target => {
    setLoading(current => ({ ...current, [target]: true }))
    setErrors(current => ({ ...current, [target]: '' }))
    try {
      const result = await api.testConnections(target)
      setResults(current => ({ ...current, [target]: result }))
    } catch (cause) {
      setErrors(current => ({ ...current, [target]: cause.message || (zh ? '连接测试失败' : 'Connection test failed') }))
    } finally { setLoading(current => ({ ...current, [target]: false })) }
  }

  useEffect(() => {
    if (autoProbeStarted.current) return
    autoProbeStarted.current = true
    void run('mcp')
  }, [])

  return <div className="connection-tests__cards">
    <DiagnosticCard icon={<CloudServerOutlined />} title={zh ? 'Host 模型测试' : 'Host model test'} description={zh ? '向当前 DeepSeek 配置发送一次极短的无工具推理请求。' : 'Sends one short tool-free request to the configured DeepSeek model.'} action={() => run('host')} loading={loading.host} error={errors.host} empty={!results.host} language={language}>
      <ProbeResult title={results.host?.host?.model || 'DeepSeek'} subtitle="Host Agent" result={results.host?.host} language={language} />
    </DiagnosticCard>
    <DiagnosticCard icon={<RobotOutlined />} title={zh ? '本地大模型测试' : 'Local model test'} description={zh ? '分别测试 Ops、Security 和 Orchestrator 使用的本地 Qwen，不连接 MCP。' : 'Tests each child Agent Qwen model without connecting to MCP.'} action={() => run('models')} loading={loading.models} error={errors.models} empty={!results.models} language={language}>
      {(results.models?.agents || []).map(agent => <ProbeResult key={agent.id} title={agent.name || agent.id} subtitle={agent.model?.model || (zh ? '本地 Qwen' : 'Local Qwen')} result={agent.model || agent} language={language} />)}
    </DiagnosticCard>
    <DiagnosticCard className="connection-test--mcp" icon={<ApiOutlined />} title={zh ? 'MCP 工具能力' : 'MCP tool capabilities'} description={zh ? '实时发现 MCP 工具，并核对每个 Agent 的实际调用权限。' : 'Discover MCP tools and inspect each Agent’s effective access.'} action={() => run('mcp')} actionLabel={zh ? '重新检测' : 'Refresh'} loading={loading.mcp} error={errors.mcp} empty={!results.mcp} language={language}>
      <div className="connection-test__overview"><span className="connection-test__overview-kicker">LIVE CAPABILITY MAP</span><strong>{connectedCount}<small> / {mcpAgents.length}</small></strong><span>{zh ? 'Agent 已连接' : 'Agents connected'}</span><span className="connection-test__overview-divider" /><strong>{uniqueTools}</strong><span>{zh ? '种 MCP 工具' : 'MCP tools'}</span></div>
      {mcpAgents.map((agent, index) => <ToolCatalog key={agent.id} agent={agent} language={language} index={index} />)}
    </DiagnosticCard>
  </div>
}
