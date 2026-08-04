import React from 'react'
import { CodeOutlined, LoadingOutlined } from '@ant-design/icons'

function json(value) {
  return typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
}

export default function ToolActivity({ tool = 'Tool call', status = 'completed', input, output, error, duration }) {
  const isRunning = status === 'running'
  const summary = error ? `${tool} failed` : isRunning ? `${tool} is running` : `${tool} completed`
  return (
    <article className={`workspace-tool workspace-tool--${status}`}>
      <div className="workspace-tool__summary">
        {isRunning ? <LoadingOutlined aria-hidden="true" /> : <CodeOutlined aria-hidden="true" />}
        <span>{summary}</span>
        {duration != null && <small>{duration}ms</small>}
      </div>
      <details>
        <summary>Raw details</summary>
        <pre>{json({ input, output, error })}</pre>
      </details>
    </article>
  )
}
