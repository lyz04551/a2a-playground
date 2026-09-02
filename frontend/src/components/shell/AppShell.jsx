import React, { useEffect, useState } from 'react'
import { Badge, Button, Drawer, Tooltip } from 'antd'
import {
  FileTextOutlined,
  DashboardOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  MoonOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  SunOutlined,
} from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import { useConsoleSettings } from '../../context/ConsoleSettingsContext'
import SettingsDrawer from './SettingsDrawer'
import CommandPalette from './CommandPalette'

const NAV_ITEMS = [
  { key: '/dashboard', icon: <DashboardOutlined />, zh: '总览', en: 'Dashboard' },
  { key: '/agents', icon: <RobotOutlined />, zh: 'Agents', en: 'Agents' },
  { key: '/workspace', icon: <MessageOutlined />, zh: '工作台', en: 'Workspace' },
  { key: '/events', icon: <FileTextOutlined />, zh: '事件', en: 'Events' },
]

function ConsoleNav({ collapsed, onNavigate }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useConsoleSettings()
  return (
    <nav className="console-nav" aria-label={settings.language === 'zh-CN' ? '主导航' : 'Main navigation'}>
      {NAV_ITEMS.map(item => {
        const active = location.pathname.startsWith(item.key)
        const label = settings.language === 'zh-CN' ? item.zh : item.en
        return (
          <Tooltip key={item.key} title={collapsed ? label : ''} placement="right">
            <button
              type="button"
              className={active ? 'is-active' : ''}
              aria-current={active ? 'page' : undefined}
              onClick={() => { navigate(item.key); onNavigate?.() }}
            >
              {item.icon}<span>{label}</span>
            </button>
          </Tooltip>
        )
      })}
    </nav>
  )
}

export default function AppShell({ children }) {
  const { settings, updateSettings } = useConsoleSettings()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(settings.sidebarCollapsed)
  const isChinese = settings.language === 'zh-CN'

  useEffect(() => setCollapsed(settings.sidebarCollapsed), [settings.sidebarCollapsed])
  useEffect(() => {
    const onKeyDown = event => {
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey) && !event.altKey) {
        event.preventDefault()
        setCommandOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    updateSettings({ sidebarCollapsed: next })
  }

  const sideContent = (
    <>
      <div className="console-brand">
        <div className="console-brand__mark">A²</div>
        <div><strong>A2A Playground</strong><small>Operations Console</small></div>
      </div>
      <ConsoleNav collapsed={collapsed} onNavigate={() => setMobileNavOpen(false)} />
      <div className="console-sidebar__status">
        <Badge status="success" />
        <span>{isChinese ? '控制台已连接' : 'Console connected'}</span>
      </div>
    </>
  )

  return (
    <div className={`console-shell ${collapsed ? 'is-collapsed' : ''}`}>
      <aside className="console-sidebar">{sideContent}</aside>
      <div className="console-stage">
        <header className="console-topbar">
          <Button
            type="text"
            className="console-topbar__desktop-toggle"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleCollapsed}
          />
          <Button
            type="text"
            className="console-topbar__mobile-toggle"
            aria-label="Open navigation"
            icon={<MenuUnfoldOutlined />}
            onClick={() => setMobileNavOpen(true)}
          />
          <button type="button" className="console-command-trigger" aria-label="Open command palette" onClick={() => setCommandOpen(true)}>
            <SearchOutlined /><span>{isChinese ? '搜索 Agent、会话和事件' : 'Search Agents, conversations and events'}</span><kbd>⌘ K</kbd>
          </button>
          <div className="console-topbar__actions">
            <Tooltip title={settings.theme === 'dark' ? 'Light theme' : 'Dark theme'}>
              <Button
                type="text"
                aria-label="Toggle theme"
                icon={settings.theme === 'dark' ? <SunOutlined /> : <MoonOutlined />}
                onClick={() => updateSettings({ theme: settings.theme === 'dark' ? 'light' : 'dark' })}
              />
            </Tooltip>
            <Button type="text" aria-label="Open settings" icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)} />
          </div>
        </header>
        <div className="console-content">{children}</div>
      </div>
      <Drawer
        className="console-mobile-drawer"
        placement="left"
        size={286}
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        closable={false}
      >
        <div className="console-mobile-nav">{sideContent}</div>
      </Drawer>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
    </div>
  )
}
