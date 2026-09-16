import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Popconfirm, Skeleton, Tag, message } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import * as api from '../api/api'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'
import { modelConfigForm, modelConfigPayload } from '../state/modelConfig'

export default function ModelSettingsPage() {
  const { settings } = useConsoleSettings()
  const zh = settings.language === 'zh-CN'
  const [form] = Form.useForm()
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const next = await api.getModelConfig()
      setConfig(next); form.setFieldsValue(modelConfigForm(next))
    } catch (cause) { setError(cause.message || (zh ? '模型配置加载失败' : 'Failed to load model configuration')) }
    finally { setLoading(false) }
  }, [form, zh])

  useEffect(() => { load() }, [load])

  const save = async values => {
    setSaving(true); setError('')
    try {
      const next = await api.updateModelConfig(modelConfigPayload(values))
      setConfig(next); form.setFieldsValue(modelConfigForm(next))
      message.success(zh ? 'Host 模型配置已保存，将用于新的运行' : 'Host model configuration saved for new runs')
    } catch (cause) { setError(cause.message || (zh ? '保存失败' : 'Save failed')) }
    finally { setSaving(false) }
  }

  const reset = async () => {
    setSaving(true); setError('')
    try {
      const next = await api.resetModelConfig()
      setConfig(next); form.setFieldsValue(modelConfigForm(next))
      message.success(zh ? '已恢复环境变量配置' : 'Environment defaults restored')
    } catch (cause) { setError(cause.message || (zh ? '恢复失败' : 'Reset failed')) }
    finally { setSaving(false) }
  }

  return <div className="model-settings console-page"><div className="console-page__inner">
    <header className="console-page-header"><div><span className="console-eyebrow">Host Agent</span><h1>{zh ? '模型设置' : 'Model settings'}</h1><p>{zh ? '仅影响之后新建的 Auto Run，不修改子 Agent。' : 'Applies only to new Auto runs, not child Agents.'}</p></div><Button icon={<ReloadOutlined />} onClick={load}>{zh ? '刷新' : 'Refresh'}</Button></header>
    {error && <Alert type="error" showIcon closable message={error} onClose={() => setError('')} />}
    <section className="console-card model-settings__card">
      {loading && !config ? <Skeleton active /> : <>
        <div className="model-settings__status"><div><small>{zh ? '配置来源' : 'Source'}</small><Tag color={config?.source === 'runtime' ? 'blue' : 'default'}>{config?.source === 'runtime' ? (zh ? '页面覆盖' : 'Runtime override') : (zh ? '环境变量' : 'Environment')}</Tag></div><div><small>API Key</small><Tag color={config?.api_key_configured ? 'green' : 'red'}>{config?.api_key_configured ? (zh ? '已配置' : 'Configured') : (zh ? '未配置' : 'Missing')}</Tag></div></div>
        <Form form={form} layout="vertical" onFinish={save} requiredMark="optional">
          <Form.Item name="provider" label="Provider" rules={[{ required: true }]}><Input placeholder="openai-compatible" /></Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true }, { type: 'url' }]}><Input placeholder="https://api.example.com/v1" /></Form.Item>
          <Form.Item name="model" label="Model" rules={[{ required: true }]}><Input placeholder="model-name" /></Form.Item>
          <Form.Item name="api_key" label="API Key" extra={zh ? '留空会保留现有密钥；密钥不会从服务器返回。' : 'Leave blank to keep the existing secret. The server never returns it.'}><Input.Password autoComplete="new-password" placeholder={config?.api_key_configured ? '••••••••' : ''} /></Form.Item>
          <div className="model-settings__actions"><Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>{zh ? '保存配置' : 'Save configuration'}</Button><Popconfirm title={zh ? '恢复环境变量中的 Host 模型配置？' : 'Restore Host model environment defaults?'} onConfirm={reset}><Button danger disabled={saving || config?.source !== 'runtime'}>{zh ? '恢复默认值' : 'Restore defaults'}</Button></Popconfirm></div>
        </Form>
      </>}
    </section>
  </div></div>
}
