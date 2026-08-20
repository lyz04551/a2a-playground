import React from 'react'
import { useMemo, useState } from 'react'
import { Button, message } from 'antd'
import { CodeOutlined, CopyOutlined, DownloadOutlined, LoadingOutlined } from '@ant-design/icons'
import { redactSensitive } from './operationSafety'

function json(value) {
  return typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
}

export default function ToolActivity({ tool = 'Tool call', status = 'completed', input, output, error, duration }) {
  const [messageApi, contextHolder] = message.useMessage()
  const isRunning = status === 'running'
  const summary = error ? `${tool} failed` : isRunning ? `${tool} is running` : `${tool} completed`
  const safeDetails = useMemo(() => redactSensitive({ input, output, error }), [input, output, error])
  const serialized = useMemo(() => json(safeDetails), [safeDetails])
  const copy = async () => {
    await navigator.clipboard.writeText(serialized)
    messageApi.success('Redacted details copied')
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([serialized], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${String(tool).replace(/[^a-z0-9_-]+/gi, '-') || 'tool'}-details.json`; anchor.click()
    URL.revokeObjectURL(url)
  }
  return (
    <article className={`workspace-tool workspace-tool--${status}`}>
      {contextHolder}
      <div className="workspace-tool__summary">
        {isRunning ? <LoadingOutlined aria-hidden="true" /> : <CodeOutlined aria-hidden="true" />}
        <span>{summary}</span>
        {duration != null && <small>{duration}ms</small>}
      </div>
      <details>
        <summary>Redacted details</summary>
        <div className="workspace-tool__actions"><Button size="small" icon={<CopyOutlined />} onClick={copy}>Copy</Button><Button size="small" icon={<DownloadOutlined />} onClick={download}>Download</Button></div>
        <pre>{serialized}</pre>
      </details>
    </article>
  )
}
