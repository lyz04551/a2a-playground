import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import * as api from '../api/api'
import { streamRun } from '../api/runStream'
import { emptyRunState, reduceRunEvent, restoreRunEventState } from '../state/runEvents'
import { buildRunReconnectCommand, restoreWorkspaceState, selectLatestConversationRun } from '../components/workspace/workspaceState'

const TERMINAL_RUN_STATUSES = new Set(['completed', 'failed', 'cancelled'])

function reducer(state, action) {
  if (action.type === 'reset') return { ...emptyRunState, messages: action.messages || [] }
  if (action.type === 'event') return reduceRunEvent(state, action.event)
  if (action.type === 'user-message') return { ...state, messages: [...state.messages, action.message] }
  if (action.type === 'approval-decision') return { ...state, approvals: state.approvals.map(approval => approval.id === action.id ? { ...approval, status: action.decision } : approval) }
  if (action.type === 'restore') return restoreRunEventState(action)
  return state
}

export default function useRunStream({ initialMode = 'auto', initialAgentId = '' } = {}) {
  const [state, dispatch] = useReducer(reducer, emptyRunState)
  const [conversationId, setConversationId] = useState(null)
  const [mode, setMode] = useState(initialMode)
  const [selectedAgentId, setSelectedAgentId] = useState(initialAgentId)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [lastCommand, setLastCommand] = useState(null)
  const [connection, setConnection] = useState({ state: 'idle', attempt: 0 })
  const abortRef = useRef(null)

  const beginNewConversation = useCallback((nextMode = mode, nextAgentId = selectedAgentId) => {
    abortRef.current?.abort()
    setConversationId(null); setMode(nextMode); setSelectedAgentId(nextAgentId)
    setError(''); setConnection({ state: 'idle', attempt: 0 }); dispatch({ type: 'reset' })
  }, [mode, selectedAgentId])

  const restoreConversation = useCallback(async (id) => {
    setLoading(true); setError(''); setConnection({ state: 'restoring', attempt: 0 })
    try {
      const conversation = await api.getConversation(id)
      const runs = await api.listRuns()
      const run = conversation.run || selectLatestConversationRun(id, runs)
      const context = restoreWorkspaceState(conversation, run)
      let approvals = context.approvals
      let tasks = context.tasks
      if (run?.id) {
        const [detailed, rawEvents] = await Promise.all([
          api.getRun(run.id),
          api.listRunEvents(run.id).catch(() => []),
        ])
        approvals = detailed.approvals || approvals
        tasks = detailed.tasks || detailed.trace || tasks
        context.rawEvents = rawEvents
      }
      setConversationId(context.conversationId); setMode(context.mode); setSelectedAgentId(context.selectedAgentId)
      dispatch({ type: 'restore', run, approvals, tasks, rawEvents: context.rawEvents || [], messages: conversation.messages || [] })
      setConnection({ state: run && !TERMINAL_RUN_STATUSES.has(run.status) ? 'recovered' : 'idle', attempt: 0 })
    } catch (cause) { setError(cause.message || 'Unable to restore this conversation.'); setConnection({ state: 'interrupted', attempt: 0 }) }
    finally { setLoading(false) }
  }, [])

  const send = useCallback(async (content) => {
    const message = content.trim()
    if (!message || loading) return
    const command = { conversation_id: conversationId || undefined, mode, message }
    if (mode === 'direct') command.target_agent_id = selectedAgentId
    setError(''); setLoading(true); setLastCommand(command); setConnection({ state: 'connecting', attempt: 0 })
    dispatch({ type: 'user-message', message: { id: `local:${Date.now()}`, role: 'user', content: message } })
    const controller = new AbortController(); abortRef.current = controller
    try {
      await streamRun(command, {
        onEvent: event => {
          if (event.conversation_id) setConversationId(current => current || event.conversation_id)
          dispatch({ type: 'event', event })
        },
        onError: cause => setError(cause.message || 'The run stream was interrupted.'),
        onReconnect: ({ attempt }) => setConnection({ state: 'reconnecting', attempt }),
        onConnectionChange: next => setConnection(next),
      }, { signal: controller.signal })
    } catch (cause) {
      if (cause.name !== 'AbortError') {
        const errorMessage = cause.message || 'Unable to start the run.'
        setError(errorMessage)
        setConnection({ state: 'interrupted', attempt: 0 })
        dispatch({ type: 'event', event: {
          version: 1,
          event_id: `stream-interrupted:${Date.now()}`,
          sequence: Number.MAX_SAFE_INTEGER,
          run_id: state.run?.id || 'pending',
          conversation_id: conversationId || 'pending',
          task_id: null,
          parent_task_id: null,
          type: 'stream.interrupted',
          timestamp: new Date().toISOString(),
          data: { error: errorMessage },
        } })
      }
    } finally { setLoading(false); abortRef.current = null }
  }, [conversationId, loading, mode, selectedAgentId, state.run?.id])

  const retry = useCallback(() => lastCommand && send(lastCommand.message), [lastCommand, send])
  const markApprovalDecision = useCallback((id, decision) => {
    dispatch({ type: 'approval-decision', id, decision })
  }, [])
  const followRun = useCallback(async runId => {
    abortRef.current?.abort()
    const afterSequence = Math.max(0, ...(state.rawEvents || []).map(event => Number(event.sequence) || 0))
    const command = buildRunReconnectCommand({ runId, afterSequence, mode, targetAgentId: selectedAgentId })
    const controller = new AbortController(); abortRef.current = controller
    setLoading(true); setError(''); setConnection({ state: 'connecting', attempt: 0 })
    try {
      await streamRun(command, {
        onEvent: event => dispatch({ type: 'event', event }),
        onError: cause => setError(cause.message || 'The run stream was interrupted.'),
        onReconnect: ({ attempt }) => setConnection({ state: 'reconnecting', attempt }),
        onConnectionChange: next => setConnection(next),
      }, { signal: controller.signal })
    } catch (cause) {
      if (cause.name !== 'AbortError') {
        setError(cause.message || 'Unable to follow the resumed run.')
        setConnection({ state: 'interrupted', attempt: 0 })
      }
    } finally {
      setLoading(false)
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [mode, selectedAgentId, state.rawEvents])
  const cancel = useCallback(async () => {
    abortRef.current?.abort()
    if (state.run?.id) {
      await api.cancelRun(state.run.id)
      dispatch({ type: 'event', event: {
        version: 1, event_id: `local-cancel:${Date.now()}`, sequence: Number.MAX_SAFE_INTEGER,
        run_id: state.run.id, conversation_id: conversationId || 'pending', task_id: null,
        parent_task_id: null, type: 'run.cancelled', timestamp: new Date().toISOString(), data: {},
      } })
    }
    setLoading(false); setConnection({ state: 'idle', attempt: 0 })
  }, [conversationId, state.run?.id])
  useEffect(() => () => abortRef.current?.abort(), [])

  const canCancel = Boolean(state.run?.id && !TERMINAL_RUN_STATUSES.has(state.run?.status))
  return useMemo(() => ({ state, conversationId, mode, setMode, selectedAgentId, setSelectedAgentId, loading, error, connection, canCancel, send, retry, cancel, beginNewConversation, restoreConversation, followRun, markApprovalDecision }), [state, conversationId, mode, selectedAgentId, loading, error, connection, canCancel, send, retry, cancel, beginNewConversation, restoreConversation, followRun, markApprovalDecision])
}
