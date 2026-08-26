import React from 'react'
import {
  CheckCircleFilled, CloseCircleFilled, CloudServerOutlined,
  ExclamationCircleFilled, LoadingOutlined, SettingOutlined,
} from '@ant-design/icons'
import { getSystemStatus } from './workspaceState'

const icons = {
  offline: CloudServerOutlined,
  settings: SettingOutlined,
  running: LoadingOutlined,
  approval: ExclamationCircleFilled,
  failure: CloseCircleFilled,
  success: CheckCircleFilled,
  unknown: ExclamationCircleFilled,
}

export default function SystemStatus({ status, className = '' }) {
  const display = getSystemStatus(status)
  const Icon = icons[display.icon]
  return (
    <span className={`workspace-status workspace-status--${display.tone} ${className}`.trim()} role="status">
      <Icon aria-hidden="true" />
      <span>{display.label}</span>
    </span>
  )
}
