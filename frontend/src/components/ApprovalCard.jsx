import React, { useState } from 'react'
import { Button } from 'antd'
import { CheckOutlined, CloseOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

export default function ApprovalCard({ approval, onDecide }) {
  const [submitting, setSubmitting] = useState('')
  const status = approval.status || 'pending'

  const decide = async decision => {
    setSubmitting(decision)
    try {
      await onDecide?.(approval, decision)
    } finally {
      setSubmitting('')
    }
  }

  return (
    <article className="approval-card">
      <div className="approval-card__eyebrow">
        <SafetyCertificateOutlined />
        Human checkpoint
        <span>{status}</span>
      </div>
      <h4>{approval.tool_name || approval.toolName}</h4>
      <p>此操作会改变 Kubernetes 集群状态，只有下方完全一致的参数会被批准。</p>
      <pre>{JSON.stringify(approval.arguments || {}, null, 2)}</pre>
      {status === 'pending' && (
        <div className="approval-card__actions">
          <Button
            danger
            icon={<CloseOutlined />}
            loading={submitting === 'rejected'}
            onClick={() => decide('rejected')}
          >
            拒绝
          </Button>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            loading={submitting === 'approved'}
            onClick={() => decide('approved')}
          >
            批准并继续
          </Button>
        </div>
      )}
    </article>
  )
}

