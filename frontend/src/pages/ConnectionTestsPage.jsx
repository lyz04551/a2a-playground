import React from 'react'
import ConnectionDiagnostics from '../components/ConnectionDiagnostics'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'

export default function ConnectionTestsPage() {
  const { settings } = useConsoleSettings()
  const zh = settings.language === 'zh-CN'
  return <div className="connection-tests console-page"><div className="console-page__inner">
    <header className="console-page-header"><div><span className="console-eyebrow">Diagnostics</span><h1>{zh ? '连接测试' : 'Connection tests'}</h1><p>{zh ? '分别验证 Host DeepSeek、本地 Qwen 与 MCP Server。所有测试均为显式触发且不会执行 Kubernetes 工具。' : 'Test Host DeepSeek, local Qwen, and MCP independently. Tests run only on demand and never execute Kubernetes tools.'}</p></div></header>
    <ConnectionDiagnostics language={settings.language} />
  </div></div>
}
