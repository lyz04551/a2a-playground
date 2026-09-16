import React, { useState } from 'react'
import { Alert, Button, Tag } from 'antd'
import { ApiOutlined } from '@ant-design/icons'

import * as api from '../api/api'
import { diagnosticView } from '../state/connectionDiagnostics'


function ProbeResult({ label, result, language, detail }) {
  const view = diagnosticView(result, language)
  return <div className="connection-diagnostics__probe">
    <div><strong>{label}</strong>{detail && <small>{detail}</small>}</div>
    <div className="connection-diagnostics__result">
      {view.latency && <small>{view.latency}</small>}
      <Tag color={view.color}>{view.label}</Tag>
    </div>
    {view.error && <code>{view.error}</code>}
  </div>
}

export default function ConnectionDiagnostics({ language = 'zh-CN' }) {
  const zh = language === 'zh-CN'
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setLoading(true); setError('')
    try { setResult(await api.testConnections()) }
    catch (cause) { setError(cause.message || (zh ? '连接诊断失败' : 'Connection diagnostics failed')) }
    finally { setLoading(false) }
  }

  return <section className="console-card model-settings__card connection-diagnostics">
    <header><div><h2>{zh ? '连接诊断' : 'Connection diagnostics'}</h2><p>{zh ? '真实测试 Host 模型、子 Agent 模型与 MCP 工具发现；不会执行 Kubernetes 工具。' : 'Tests Host and child models plus MCP discovery without executing Kubernetes tools.'}</p></div><Button type="primary" icon={<ApiOutlined />} loading={loading} onClick={run}>{zh ? '全部测试' : 'Test all'}</Button></header>
    {error && <Alert type="error" showIcon message={error} />}
    {!result && !error && <p className="connection-diagnostics__empty">{zh ? '尚未运行连接测试。' : 'Connections have not been tested yet.'}</p>}
    {result && <div className="connection-diagnostics__groups">
      <section><h3>Host Agent</h3><ProbeResult label={result.host?.model || 'DeepSeek'} result={result.host} language={language} detail={zh ? '真实无工具推理' : 'Real inference without tools'} /></section>
      {(result.agents || []).map(agent => <section key={agent.id}>
        <h3>{agent.name || agent.id}</h3>
        {agent.state === 'offline' || agent.state === 'unsupported'
          ? <ProbeResult label={zh ? 'Agent 诊断端点' : 'Agent diagnostics'} result={agent} language={language} />
          : <>
            <ProbeResult label={agent.model?.model || (zh ? '本地 Qwen' : 'Local Qwen')} result={agent.model} language={language} detail={zh ? '真实无工具推理' : 'Real inference without tools'} />
            <ProbeResult label="MCP Server" result={agent.mcp} language={language} detail={agent.mcp?.tool_count == null ? '' : (zh ? `${agent.mcp.tool_count} 个工具` : `${agent.mcp.tool_count} tools`)} />
          </>}
      </section>)}
    </div>}
  </section>
}
