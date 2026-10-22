import React from 'react'
import ConnectionDiagnostics from '../components/ConnectionDiagnostics'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'

export default function ConnectionTestsPage() {
  const { settings } = useConsoleSettings()
  const zh = settings.language === 'zh-CN'
  return <div className="connection-tests console-page"><div className="console-page__inner">
    <header className="console-page-header"><div><span className="console-eyebrow">Diagnostics</span><h1>{zh ? '连接与工具能力' : 'Connections and tools'}</h1><p>{zh ? '打开页面时自动发现 MCP 工具；模型测试由你手动触发。工具发现不会执行 Kubernetes 工具。' : 'MCP tools are discovered when this page opens. Model tests run on demand. Discovery does not execute Kubernetes tools.'}</p></div></header>
    <ConnectionDiagnostics language={settings.language} />
  </div></div>
}
