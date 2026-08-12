import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Input, Modal, Tag, message } from 'antd'
import { CheckCircleOutlined, PlusOutlined } from '@ant-design/icons'
import * as api from '../../api/api'

export default function AddAgentModal({ open, onClose, onAdded, zh }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { if (!open) { setUrl(''); setInfo(null); setError('') } }, [open])
  const fetchCard = async () => {
    if (!url.trim()) return
    setLoading(true); setError(''); setInfo(null)
    try { setInfo(await api.fetchAgentCard(url.trim())) }
    catch (cause) { setError(cause.message || String(cause)) }
    finally { setLoading(false) }
  }
  const save = async () => {
    setLoading(true); setError('')
    try {
      await api.registerAgent(url.trim())
      message.success(zh ? '智能体已添加' : 'Agent added')
      await onAdded(); onClose()
    } catch (cause) { setError(cause.message || String(cause)) }
    finally { setLoading(false) }
  }

  return <Modal title={<span><PlusOutlined /> {zh ? '添加 A2A 智能体' : 'Add A2A agent'}</span>} open={open} onCancel={onClose} footer={null} width={520} destroyOnClose>
    <label className="agent-url-label">{zh ? '智能体地址' : 'Agent URL'}</label>
    <Input.Search value={url} onChange={event => { setUrl(event.target.value); setInfo(null); setError('') }} onSearch={fetchCard} disabled={loading} size="large"
      placeholder={zh ? '例如 localhost:10001' : 'e.g. localhost:10001'} enterButton={<Button loading={loading}>{zh ? '读取 Card' : 'Fetch card'}</Button>} />
    {error && <Alert type="error" showIcon message={error} />}
    {info && <Card size="small" className="agent-card-preview">
      <div className="agent-preview-title"><CheckCircleOutlined /><strong>{zh ? 'Agent Card 已读取' : 'Agent Card loaded'}</strong></div>
      <h3>{info.name || 'N/A'}</h3><p>{info.description}</p>
      <div>{info.version && <Tag>{info.version}</Tag>}{info.capabilities?.streaming && <Tag color="green">Streaming</Tag>}{info.provider?.organization && <Tag>{info.provider.organization}</Tag>}</div>
    </Card>}
    <div className="agent-modal-actions"><Button onClick={onClose}>{zh ? '取消' : 'Cancel'}</Button>{info && <Button type="primary" loading={loading} onClick={save}>{zh ? '添加智能体' : 'Add agent'}</Button>}</div>
  </Modal>
}
