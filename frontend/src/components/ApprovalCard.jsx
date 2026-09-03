import React, { useState } from 'react'
import { Button, Tag } from 'antd'
import { CheckOutlined, CloseOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { approvalRisk, diffArguments, formatArgumentValue, redactSensitive } from './workspace/operationSafety'

export default function ApprovalCard({ approval, previousApproval, onDecide, language = 'zh-CN' }) {
  const [submitting, setSubmitting] = useState('')
  const status = approval.status || 'pending'
  const zh = language.startsWith('zh')
  const risk = approvalRisk(approval)
  const differences = previousApproval ? diffArguments(previousApproval.arguments, approval.arguments) : []

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
        <Tag color={risk === 'critical' || risk === 'high' ? 'red' : 'orange'}>{risk.toUpperCase()}</Tag>
      </div>
      <h4>{approval.tool_name || approval.toolName}</h4>
      <p>{zh ? '此操作会改变 Kubernetes 集群状态，只有下方完全一致的参数会被批准。' : 'This changes cluster state. Approval applies only to these exact arguments.'}</p>
      {approval.action_digest && <small className="approval-card__digest">Digest: {approval.action_digest}</small>}
      <pre>{JSON.stringify(redactSensitive(approval.arguments || {}), null, 2)}</pre>
      {previousApproval && <details className="approval-card__diff" open={differences.length > 0}>
        <summary>{zh ? `与上次请求相比（${differences.length} 项变化）` : `Compared with previous request (${differences.length} changes)`}</summary>
        {differences.length === 0 ? <p>{zh ? '参数未变化。' : 'No argument changes.'}</p> : (
          <ul className="approval-card__diff-list">
            {differences.map(item => (
              <li key={item.path} className={`is-${item.kind}`}>
                <code>{item.path}</code>
                <div className="approval-card__diff-value">
                  {item.kind !== 'added' && <section><small>{zh ? '之前' : 'Before'}</small><pre>{formatArgumentValue(item.before)}</pre></section>}
                  {item.kind !== 'removed' && <section><small>{zh ? '现在' : 'After'}</small><pre>{formatArgumentValue(item.after)}</pre></section>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </details>}
      {status === 'pending' && (
        <div className="approval-card__actions">
          <Button
            danger
            icon={<CloseOutlined />}
            loading={submitting === 'rejected'}
            onClick={() => decide('rejected')}
          >
            {zh ? '拒绝' : 'Reject'}
          </Button>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            loading={submitting === 'approved'}
            onClick={() => decide('approved')}
          >
            {zh ? '批准并继续' : 'Approve and continue'}
          </Button>
        </div>
      )}
    </article>
  )
}
