import React from 'react'
import { Card, Col, Row, Statistic } from 'antd'
import { ApiOutlined, RobotOutlined, TagsOutlined, ThunderboltOutlined } from '@ant-design/icons'

export default function AgentStats({ stats, zh }) {
  const items = [
    { key: 'total', label: zh ? '智能体总数' : 'Total agents', value: stats.total, icon: <RobotOutlined />, color: '#10b981' },
    { key: 'streaming', label: zh ? '流式响应' : 'Streaming', value: stats.streaming, suffix: `/ ${stats.total}`, icon: <ThunderboltOutlined />, color: '#f59e0b' },
    { key: 'skills', label: zh ? 'Skills 总数' : 'Total skills', value: stats.skills, icon: <TagsOutlined />, color: '#6366f1' },
    { key: 'protocol', label: zh ? '协议' : 'Protocol', value: 'A2A', icon: <ApiOutlined />, color: '#06b5ce' },
  ]
  return <Row gutter={[16, 16]} className="agent-stats">
    {items.map(item => <Col xs={12} lg={6} key={item.key}>
      <Card size="small" hoverable>
        <Statistic title={item.label} value={item.value} suffix={item.suffix} prefix={React.cloneElement(item.icon, { style: { color: item.color } })} />
      </Card>
    </Col>)}
  </Row>
}
