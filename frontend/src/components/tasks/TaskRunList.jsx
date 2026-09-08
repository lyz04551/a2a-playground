import React from 'react'
import { Input, Select, Tag } from 'antd'

export default function TaskRunList({ runs, selectedId, filters, agents, onFilters, onSelect, zh }) {
  return <aside className="task-run-list">
    <div className="task-run-list__filters">
      <Input allowClear placeholder={zh ? '搜索 Run、目标或 Agent' : 'Search runs'} value={filters.query} onChange={event => onFilters({ ...filters, query: event.target.value })} />
      <div><Select value={filters.mode} onChange={mode => onFilters({ ...filters, mode })} options={[{ value: 'all', label: zh ? '全部模式' : 'All modes' }, { value: 'auto', label: 'Auto' }, { value: 'direct', label: 'Direct' }]} /><Select value={filters.status} onChange={status => onFilters({ ...filters, status })} options={['all', 'running', 'approval_required', 'completed', 'failed', 'cancelled'].map(value => ({ value, label: value === 'all' ? (zh ? '全部状态' : 'All states') : value }))} /></div>
      <Select value={filters.agent} onChange={agent => onFilters({ ...filters, agent })} options={[{ value: 'all', label: zh ? '全部 Agent' : 'All agents' }, ...agents.map(agent => ({ value: agent.id, label: agent.name || agent.id }))]} />
    </div>
    <div className="task-run-list__items">{runs.map(run => <button type="button" className={run.id === selectedId ? 'is-selected' : ''} key={run.id} onClick={() => onSelect(run.id)}><span><Tag color={(run.mode || 'auto') === 'auto' ? 'blue' : 'green'}>{run.mode || 'auto'}</Tag><small>{run.status || 'unknown'}</small></span><strong>{run.title || run.request || run.id}</strong><code>{run.id}</code></button>)}</div>
  </aside>
}
