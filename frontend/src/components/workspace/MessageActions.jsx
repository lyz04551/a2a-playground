import React from 'react'
import { Button, Tooltip, message } from 'antd'
import { CheckOutlined, CopyOutlined } from '@ant-design/icons'

export default function MessageActions({ content = '', language = 'zh-CN' }) {
  const [copied, setCopied] = React.useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      message.success(language === 'zh-CN' ? '消息已复制' : 'Message copied')
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      message.error(language === 'zh-CN' ? '复制失败，请手动选择内容' : 'Unable to copy this message')
    }
  }
  return <Tooltip title={language === 'zh-CN' ? '复制消息' : 'Copy message'}><Button type="text" size="small" aria-label="Copy message" icon={copied ? <CheckOutlined /> : <CopyOutlined />} onClick={copy} disabled={!content} /></Tooltip>
}
