import React from 'react'
import { Button, Descriptions, Drawer, Empty, Tag, message } from 'antd'
import { CopyOutlined } from '@ant-design/icons'

export default function EventDetailDrawer({ event, open, onClose }) {
  const raw = event ? JSON.stringify(event, null, 2) : ''
  const copy = async () => {
    try { await navigator.clipboard.writeText(raw); message.success('事件 JSON 已复制') }
    catch { message.error('复制失败，请手动选择内容') }
  }
  return (
    <Drawer title="事件详情" open={open} onClose={onClose} size={560} extra={<Button icon={<CopyOutlined />} onClick={copy} disabled={!event}>复制 JSON</Button>}>
      {!event ? <Empty description="未选择事件" /> : <div className="event-detail-drawer">
        <Descriptions column={1} size="small" bordered items={[
          { key: 'type', label: '事件类型', children: <Tag>{event.event_type || event.type || 'unknown'}</Tag> },
          { key: 'state', label: '状态', children: event.state || 'unknown' },
          { key: 'conversation', label: 'Conversation ID', children: <code>{event.conversation_id || '—'}</code> },
          { key: 'task', label: 'Task ID', children: <code>{event.task_id || '—'}</code> },
          { key: 'agent', label: 'Agent', children: event.agent_name || event.agent_id || 'Host Agent' },
          { key: 'time', label: '时间', children: event.timestamp || event.created_at || '—' },
        ]} />
        <div className="event-detail-drawer__json"><span className="console-eyebrow">Raw JSON</span><pre>{raw}</pre></div>
      </div>}
    </Drawer>
  )
}
