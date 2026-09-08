import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Empty, Spin, Statistic } from 'antd'
import { BranchesOutlined, ReloadOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import * as api from '../api/api'
import { useConsoleSettings } from '../context/ConsoleSettingsContext'
import { restoreRunEventState } from '../state/runEvents'
import { buildTaskFlow, filterTaskRuns, summarizeTaskRun } from '../state/taskExplorer'
import TaskRunList from '../components/tasks/TaskRunList'
import TaskFlow from '../components/tasks/TaskFlow'
import TaskNodeDrawer from '../components/tasks/TaskNodeDrawer'

const initialFilters = { mode: 'all', status: 'all', agent: 'all', query: '' }

export default function TasksPage() {
  const { settings } = useConsoleSettings()
  const zh = settings.language === 'zh-CN'
  const [params, setParams] = useSearchParams()
  const [runs, setRuns] = useState([])
  const [agents, setAgents] = useState([])
  const [state, setState] = useState(null)
  const [filters, setFilters] = useState(initialFilters)
  const [selectedNode, setSelectedNode] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const selectedId = params.get('run') || ''

  const loadList = useCallback(async () => {
    const [nextRuns, nextAgents] = await Promise.all([api.listRuns(), api.listAgents()])
    setRuns(nextRuns); setAgents(nextAgents)
    if (!params.get('run') && nextRuns[0]) setParams({ run: nextRuns[0].id }, { replace: true })
  }, [params, setParams])

  const loadSelected = useCallback(async id => {
    if (!id) { setState(null); return }
    const [run, events] = await Promise.all([api.getRun(id), api.listRunEvents(id)])
    setState(restoreRunEventState({ run, tasks: run.tasks || [], approvals: run.approvals || [], rawEvents: events }))
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try { await loadList(); if (selectedId) await loadSelected(selectedId) }
    catch (cause) { setError(cause.message || (zh ? 'Task 数据加载失败' : 'Failed to load tasks')) }
    finally { setLoading(false) }
  }, [loadList, loadSelected, selectedId, zh])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!selectedId || !['running', 'planning', 'approval_required'].includes(state?.run?.status)) return undefined
    const timer = setInterval(() => loadSelected(selectedId).catch(() => {}), 3000)
    return () => clearInterval(timer)
  }, [selectedId, state?.run?.status, loadSelected])

  const visibleRuns = useMemo(() => filterTaskRuns(runs, filters), [runs, filters])
  const nodes = useMemo(() => state ? buildTaskFlow(state, agents) : [], [state, agents])
  const stats = useMemo(() => summarizeTaskRun(state || {}), [state])
  const chooseRun = id => { setSelectedNode(null); setParams({ run: id }) }

  return <div className="task-explorer console-page">
    <div className="console-page__inner">
      <header className="console-page-header"><div><span className="console-eyebrow">A2A Task Explorer</span><h1>{zh ? '任务流转' : 'Task flows'}</h1><p>{zh ? '查看 Host、Agent、MCP 工具和人工审批之间的完整关系。' : 'Inspect Host, Agent, MCP tool, and approval relationships.'}</p></div><Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>{zh ? '刷新' : 'Refresh'}</Button></header>
      {error && <Alert type="error" showIcon message={error} />}
      <section className="task-explorer__layout console-card">
        <TaskRunList runs={visibleRuns} selectedId={selectedId} filters={filters} agents={agents} onFilters={setFilters} onSelect={chooseRun} zh={zh} />
        <main className="task-explorer__main">
          {state && <><header className="task-explorer__summary"><div><strong>{state.run?.title || state.run?.request || state.run?.id}</strong><code>{state.run?.id}</code></div>{Object.entries(stats).map(([label, value]) => <Statistic key={label} title={label} value={value} />)}</header><div className="task-explorer__flow"><TaskFlow nodes={nodes} selectedId={selectedNode?.id} onSelect={setSelectedNode} zh={zh} /></div></>}
          {loading && !state && <div className="task-explorer__empty"><Spin /></div>}
          {!loading && !state && <Empty image={<BranchesOutlined />} description={zh ? '暂无 Run' : 'No runs'} />}
        </main>
      </section>
    </div>
    <TaskNodeDrawer node={selectedNode} events={state?.rawEvents || []} open={Boolean(selectedNode)} onClose={() => setSelectedNode(null)} zh={zh} />
  </div>
}
