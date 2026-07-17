import React from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, ConfigProvider } from 'antd'
import { RobotOutlined, MessageOutlined, FileTextOutlined, ApiOutlined } from '@ant-design/icons'
import AgentsPage from './pages/AgentsPage'
import ChatPage from './pages/ChatPage'
import EventsPage from './pages/EventsPage'
import MultiAgentPage from './pages/MultiAgentPage'

const { Sider, Content } = Layout

const NAV_ITEMS = [
  { key: '/', icon: <RobotOutlined />, label: 'Agents' },
  { key: '/chat', icon: <MessageOutlined />, label: 'Chat' },
  { key: '/events', icon: <FileTextOutlined />, label: 'Events' },
  { key: '/multi', icon: <ApiOutlined />, label: 'Multi' },
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = location.pathname === '/' ? '/'
    : location.pathname.startsWith('/chat') ? '/chat'
    : location.pathname.startsWith('/events') ? '/events'
    : location.pathname.startsWith('/multi') ? '/multi'
    : '/'

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#10b981',
          borderRadius: 8, fontSize: 15,

        },
      }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          width={220}
          theme="light"
          style={{ borderRight: '1px solid #f0f0f0' }}
        >
          <div style={{
            padding: '24px 16px',
            borderBottom: '1px solid #e5e7eb',
            background: 'linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 40, height: 40, borderRadius: 10, fontSize: 18,

                background: 'linear-gradient(135deg, #34d399, #059669)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontWeight: 700,
                boxShadow: '0 2px 8px rgba(16,185,129,0.3)',
              }}>A</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 18 }}><span style={{ color: "#10b981" }}>A2A</span> Playground</div>
                <div style={{ fontSize: 10, color: '#9ca3af' }}>Agent-to-Agent Protocol</div>
              </div>
            </div>
          </div>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={NAV_ITEMS}
            onClick={({ key }) => navigate(key)}
            style={{ borderInlineEnd: 0, marginTop: 4 }}
          />
        </Sider>
        <Content style={{ overflow: 'auto', background: 'linear-gradient(135deg, #f9fafb 0%, #f0fdf4 50%, #f9fafb 100%)' }}>
          <Routes>
            <Route path="/" element={<AgentsPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:agentId" element={<ChatPage />} />
            <Route path="/events" element={<EventsPage />} />
          <Route path="/multi" element={<MultiAgentPage />} />
          </Routes>
        </Content>
      </Layout>
    </ConfigProvider>
  )
}
