import React from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, ConfigProvider } from 'antd'
import {
  RobotOutlined, MessageOutlined, FileTextOutlined, ApiOutlined,
  GithubOutlined,
} from '@ant-design/icons'
import AgentsPage from './pages/AgentsPage'
import ChatPage from './pages/ChatPage'
import EventsPage from './pages/EventsPage'
import MultiAgentPage from './pages/MultiAgentPage'

const { Sider, Content } = Layout

const NAV_ITEMS = [
  { key: '/', icon: <RobotOutlined />, label: 'Agents' },
  { key: '/chat', icon: <MessageOutlined />, label: 'Chat' },
  { key: '/events', icon: <FileTextOutlined />, label: 'Events' },
  { key: '/multi', icon: <ApiOutlined />, label: 'Multi-Agent' },
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
          borderRadius: 10,
          fontSize: 14,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
          colorBgContainer: '#ffffff',
          colorBgElevated: '#ffffff',
          colorBorder: '#f0f0f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
        },
        components: {
          Menu: {
            itemBg: 'transparent',
            itemBorderRadius: 8,
            itemMarginInline: 8,
            itemMarginBlock: 2,
            itemHeight: 42,
            itemColor: '#64748b',
            itemSelectedColor: '#10b981',
            itemSelectedBg: '#f0fdf4',
            itemHoverBg: '#f8fafc',
            itemHoverColor: '#10b981',
          },
          Button: {
            primaryShadow: '0 2px 8px rgba(16,185,129,0.25)',
          },
          Card: {
            paddingLG: 20,
          },
        },
      }}
    >
      <Layout style={{ minHeight: '100vh', background: '#f8fafc' }}>
        <Sider
          width={240}
          theme="light"
          style={{
            borderRight: '1px solid #f0f0f0',
            background: '#ffffff',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            zIndex: 100,
          }}
        >
          {/* Logo Area */}
          <div style={{
            padding: '28px 20px 20px',
            borderBottom: '1px solid #f1f5f9',
            background: 'linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 42, height: 42, borderRadius: 12, fontSize: 18,
                background: 'linear-gradient(135deg, #34d399, #059669)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontWeight: 800,
                boxShadow: '0 4px 12px rgba(16,185,129,0.3)',
                letterSpacing: -1,
              }}>A²</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 17, letterSpacing: -0.3 }}>
                  <span style={{ color: '#10b981' }}>A2A</span>{' '}
                  <span style={{ color: '#1e293b' }}>Playground</span>
                </div>
                <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 500, letterSpacing: 0.3, textTransform: 'uppercase' }}>
                  Agent-to-Agent Protocol
                </div>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={NAV_ITEMS}
            onClick={({ key }) => navigate(key)}
            style={{ borderInlineEnd: 0, marginTop: 8, padding: '0 4px' }}
          />

          {/* Bottom info */}
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            padding: '16px 20px',
            borderTop: '1px solid #f1f5f9',
            background: '#fafbfc',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#94a3b8' }}>
              <GithubOutlined style={{ fontSize: 14 }} />
              <span>a2aproject/a2a-samples</span>
            </div>
          </div>
        </Sider>

        {/* Main Content */}
        <Content style={{
          marginLeft: 240,
          overflow: 'auto',
          minHeight: '100vh',
          background: 'linear-gradient(135deg, #f8fafc 0%, #f0fdf4 30%, #f8fafc 100%)',
        }}>
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
