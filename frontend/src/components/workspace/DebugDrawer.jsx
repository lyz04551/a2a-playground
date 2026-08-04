import React, { useMemo } from 'react'
import { Button, Drawer, Empty, Segmented, message } from 'antd'
import { CopyOutlined } from '@ant-design/icons'

function formatElapsed(events) {
  const times = events.map(event => Date.parse(event.timestamp)).filter(Number.isFinite)
  if (times.length < 2) return '—'
  return `${((Math.max(...times) - Math.min(...times)) / 1000).toFixed(2)} s`
}

export default function DebugDrawer({ open, onClose, run = {}, events = [], language = 'zh-CN' }) {
  const [view, setView] = React.useState('events')
  const zh = language === 'zh-CN'
  const lastTaskId = [...events].reverse().find(event => event.task_id)?.task_id || '—'
  const usage = [...events].reverse().find(event => event.data?.usage)?.data?.usage
  const json = useMemo(() => JSON.stringify(view === 'events' ? events : run, null, 2), [events, run, view])

  const copy = async () => {
    try { await navigator.clipboard.writeText(json); message.success(zh ? 'JSON 已复制' : 'JSON copied') }
    catch { message.error(zh ? '复制失败' : 'Unable to copy JSON') }
  }

  return (
    <Drawer title={zh ? '运行调试信息' : 'Run debugger'} open={open} onClose={onClose} size={560}>
      <div className="debug-summary">
        <div><span>Run ID</span><code>{run.id || '—'}</code></div>
        <div><span>Task ID</span><code>{lastTaskId}</code></div>
        <div><span>{zh ? '事件数' : 'Events'}</span><strong>{events.length}</strong></div>
        <div><span>{zh ? '耗时' : 'Elapsed'}</span><strong>{formatElapsed(events)}</strong></div>
        <div><span>Token</span><strong>{usage?.total_tokens ?? usage?.totalTokens ?? (zh ? '暂无数据' : 'Unavailable')}</strong></div>
      </div>
      <div className="debug-toolbar"><Segmented value={view} onChange={setView} options={[{ value: 'events', label: zh ? 'SSE 事件' : 'SSE events' }, { value: 'run', label: zh ? '运行状态' : 'Run state' }]} /><Button icon={<CopyOutlined />} onClick={copy}>{zh ? '复制 JSON' : 'Copy JSON'}</Button></div>
      {view === 'events' && events.length === 0 ? <Empty description={zh ? '暂无原始事件' : 'No raw events'} /> : <pre className="debug-json">{json}</pre>}
    </Drawer>
  )
}
