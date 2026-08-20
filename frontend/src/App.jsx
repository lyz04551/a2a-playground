import React, { lazy, Suspense } from 'react'
import { ConfigProvider, Spin, theme } from 'antd'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/shell/AppShell'
import { useConsoleSettings } from './context/ConsoleSettingsContext'

const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const EventsPage = lazy(() => import('./pages/EventsPage'))
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))

export default function App() {
  const { settings } = useConsoleSettings()
  const dark = settings.theme === 'dark'
  const compact = settings.density === 'compact'

  return (
    <ConfigProvider theme={{
      algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: dark ? '#4adea5' : '#047857',
        colorInfo: dark ? '#71b8ff' : '#0b70b5',
        colorBgBase: dark ? '#0b1220' : '#f3f6fa',
        colorBgContainer: dark ? '#111c2e' : '#ffffff',
        colorBorder: dark ? '#2a3a52' : '#dce3ec',
        colorText: dark ? '#edf4ff' : '#172033',
        borderRadius: 10,
        controlHeight: compact ? 34 : 40,
        fontSize: compact ? 13 : 14,
        fontFamily: "'Avenir Next', 'Segoe UI', sans-serif",
      },
      components: {
        Button: { primaryShadow: '0 6px 18px rgba(4, 120, 87, .2)' },
        Card: { paddingLG: compact ? 16 : 20 },
        Drawer: { colorBgElevated: dark ? '#111c2e' : '#ffffff' },
      },
    }}>
      <AppShell>
        <Suspense fallback={<div className="route-loading"><Spin size="large" /></div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/agents" element={<AgentsPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/chat" element={<Navigate to="/workspace?mode=direct" replace />} />
            <Route path="/chat/:agentId" element={<LegacyChatRedirect />} />
            <Route path="/multi" element={<Navigate to="/workspace?mode=auto" replace />} />
            <Route path="*" element={<Navigate to="/workspace" replace />} />
          </Routes>
        </Suspense>
      </AppShell>
    </ConfigProvider>
  )
}

function LegacyChatRedirect() {
  const { pathname } = useLocation()
  return <Navigate to={`/workspace?mode=direct&agent=${encodeURIComponent(pathname.split('/').pop())}`} replace />
}
