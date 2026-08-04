import React from 'react'
import { Button, Drawer, Radio, Switch } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useConsoleSettings } from '../../context/ConsoleSettingsContext'

const COPY = {
  'zh-CN': {
    title: '界面设置', appearance: '外观', light: '亮色', dark: '暗色',
    density: '信息密度', comfortable: '舒适', compact: '紧凑',
    language: '语言', collapsed: '默认折叠侧栏', reset: '恢复默认设置',
  },
  'en-US': {
    title: 'Interface settings', appearance: 'Appearance', light: 'Light', dark: 'Dark',
    density: 'Density', comfortable: 'Comfortable', compact: 'Compact',
    language: 'Language', collapsed: 'Collapse sidebar by default', reset: 'Reset settings',
  },
}

export default function SettingsDrawer({ open, onClose }) {
  const { settings, updateSettings, resetSettings } = useConsoleSettings()
  const copy = COPY[settings.language]

  return (
    <Drawer title={copy.title} open={open} onClose={onClose} size={390}>
      <div className="console-settings">
        <section>
          <label>{copy.appearance}</label>
          <Radio.Group
            block
            optionType="button"
            value={settings.theme}
            onChange={event => updateSettings({ theme: event.target.value })}
            options={[{ label: copy.light, value: 'light' }, { label: copy.dark, value: 'dark' }]}
          />
        </section>
        <section>
          <label>{copy.density}</label>
          <Radio.Group
            block
            optionType="button"
            value={settings.density}
            onChange={event => updateSettings({ density: event.target.value })}
            options={[
              { label: copy.comfortable, value: 'comfortable' },
              { label: copy.compact, value: 'compact' },
            ]}
          />
        </section>
        <section>
          <label>{copy.language}</label>
          <Radio.Group
            block
            optionType="button"
            value={settings.language}
            onChange={event => updateSettings({ language: event.target.value })}
            options={[{ label: '中文', value: 'zh-CN' }, { label: 'English', value: 'en-US' }]}
          />
        </section>
        <section className="console-settings__switch">
          <label htmlFor="sidebar-default">{copy.collapsed}</label>
          <Switch
            id="sidebar-default"
            checked={settings.sidebarCollapsed}
            onChange={checked => updateSettings({ sidebarCollapsed: checked })}
          />
        </section>
        <Button icon={<ReloadOutlined />} onClick={resetSettings}>{copy.reset}</Button>
      </div>
    </Drawer>
  )
}
