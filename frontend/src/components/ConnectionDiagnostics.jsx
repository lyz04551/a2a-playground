import React, { useState } from 'react'
import { Alert, Button, Tag } from 'antd'
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

function DiagnosticCard({ icon, title, description, action, loading, error, children, empty, language }) {
  const zh = language === 'zh-CN'
  return <section className="console-card connection-test">
    <header><div className="connection-test__heading"><span>{icon}</span><div><h2>{title}</h2><p>{description}</p></div></div><Button type="primary" loading={loading} onClick={action}>{zh ? '开始测试' : 'Run test'}</Button></header>
    {error && <Alert type="error" showIcon message={error} />}
    {empty && !error ? <p className="connection-test__empty">{zh ? '尚未运行此项测试。' : 'This test has not been run.'}</p> : <div className="connection-test__results">{children}</div>}
  </section>
}

export default function ConnectionDiagnostics({ language = 'zh-CN' }) {
  const zh = language === 'zh-CN'
  const [results, setResults] = useState({ host: null, models: null, mcp: null })
  const [loading, setLoading] = useState({ host: false, models: false, mcp: false })
  const [errors, setErrors] = useState({ host: '', models: '', mcp: '' })

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

  return <div className="connection-tests__cards">
    <DiagnosticCard icon={<CloudServerOutlined />} title={zh ? 'Host 模型测试' : 'Host model test'} description={zh ? '向当前 DeepSeek 配置发送一次极短的无工具推理请求。' : 'Sends one short tool-free request to the configured DeepSeek model.'} action={() => run('host')} loading={loading.host} error={errors.host} empty={!results.host} language={language}>
      <ProbeResult title={results.host?.host?.model || 'DeepSeek'} subtitle="Host Agent" result={results.host?.host} language={language} />
    </DiagnosticCard>
    <DiagnosticCard icon={<RobotOutlined />} title={zh ? '本地大模型测试' : 'Local model test'} description={zh ? '分别测试 Ops、Security 和 Orchestrator 使用的本地 Qwen，不连接 MCP。' : 'Tests each child Agent Qwen model without connecting to MCP.'} action={() => run('models')} loading={loading.models} error={errors.models} empty={!results.models} language={language}>
      {(results.models?.agents || []).map(agent => <ProbeResult key={agent.id} title={agent.name || agent.id} subtitle={agent.model?.model || (zh ? '本地 Qwen' : 'Local Qwen')} result={agent.model || agent} language={language} />)}
    </DiagnosticCard>
    <DiagnosticCard icon={<ApiOutlined />} title="MCP Server 测试" description={zh ? '分别执行 MCP 工具发现，仅列出工具，不调用任何 Kubernetes 工具。' : 'Runs MCP discovery only and never executes a Kubernetes tool.'} action={() => run('mcp')} loading={loading.mcp} error={errors.mcp} empty={!results.mcp} language={language}>
      {(results.mcp?.agents || []).map(agent => <ProbeResult key={agent.id} title={agent.name || agent.id} subtitle="MCP Server" result={agent.mcp || agent} language={language} detail={agent.mcp?.tool_count == null ? '' : (zh ? `${agent.mcp.tool_count} 个工具` : `${agent.mcp.tool_count} tools`)} />)}
    </DiagnosticCard>
  </div>
}
