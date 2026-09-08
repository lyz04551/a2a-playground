import React from 'react'
import { Drawer, Tag } from 'antd'
import { redactSensitive } from '../workspace/operationSafety'

export default function TaskNodeDrawer({ node, events, open, onClose, zh }) {
  const related = node ? events.filter(event => event.task_id === node.data?.id || event.data?.id === node.data?.id || event.data?.approval_id === node.data?.id) : []
  return <Drawer className="task-node-drawer" width={620} title={node?.title || (zh ? '节点详情' : 'Node details')} open={open} onClose={onClose}>
    {node && <><Tag>{node.kind}</Tag> <Tag>{node.status}</Tag>{node.subtitle && <p>{node.subtitle}</p>}<h3>{zh ? '完整内容' : 'Content'}</h3><pre>{JSON.stringify(redactSensitive(node.data || {}), null, 2)}</pre><h3>{zh ? '相关原始事件' : 'Related raw events'}</h3><pre>{related.length ? JSON.stringify(redactSensitive(related), null, 2) : (zh ? '无' : 'None')}</pre></>}
  </Drawer>
}
