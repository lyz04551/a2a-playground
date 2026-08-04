import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import * as api from '../api/api'
import { streamRun } from '../api/runStream'
import { emptyRunState, reduceRunEvent } from '../state/runEvents'
import { restoreWorkspaceState, selectLatestConversationRun } from '../components/workspace/workspaceState'

function reducer(state, action) {
  if (action.type === 'reset') return { ...emptyRunState, messages: action.messages || [] }
  if (action.type === 'event') return reduceRunEvent(state, action.event)
  if (action.type === 'user-message') return { ...state, messages: [...state.messages, action.message] }
  if (action.type === 'restore') return { ...emptyRunState, run: action.run || null, messages: action.messages || [], approvals: action.approvals || [], rawEvents: action.rawEvents || [], tasksById: Object.fromEntries((action.tasks || []).map(task => [task.id, task])), taskOrder: (action.tasks || []).map(task => task.id) }
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
  const abortRef = useRef(null)

  const beginNewConversation = useCallback((nextMode = mode, nextAgentId = selectedAgentId) => {
    abortRef.current?.abort()
    setConversationId(null); setMode(nextMode); setSelectedAgentId(nextAgentId)
    setError(''); dispatch({ type: 'reset' })
  }, [mode, selectedAgentId])

  const restoreConversation = useCallback(async (id) => {
    setLoading(true); setError('')
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
    } catch (cause) { setError(cause.message || 'Unable to restore this conversation.') }
    finally { setLoading(false) }
  }, [])

  const send = useCallback(async (content) => {
    const message = content.trim()
    if (!message || loading) return
    const command = { conversation_id: conversationId || undefined, mode, message }
    if (mode === 'direct') command.target_agent_id = selectedAgentId
    setError(''); setLoading(true); setLastCommand(command)
    dispatch({ type: 'user-message', message: { id: `local:${Date.now()}`, role: 'user', content: message } })
    const controller = new AbortController(); abortRef.current = controller
    try {
      await streamRun(command, {
        onEvent: event => {
          if (event.conversation_id) setConversationId(current => current || event.conversation_id)
          dispatch({ type: 'event', event })
        },
        onError: cause => setError(cause.message || 'The run stream was interrupted.'),
      }, { signal: controller.signal })
    } catch (cause) {
      if (cause.name !== 'AbortError') {
        const errorMessage = cause.message || 'Unable to start the run.'
        setError(errorMessage)
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
  const cancel = useCallback(async () => {
    abortRef.current?.abort()
    if (state.run?.id) await api.cancelRun(state.run.id)
  }, [state.run?.id])
  useEffect(() => () => abortRef.current?.abort(), [])

  return useMemo(() => ({ state, conversationId, mode, setMode, selectedAgentId, setSelectedAgentId, loading, error, send, retry, cancel, beginNewConversation, restoreConversation }), [state, conversationId, mode, selectedAgentId, loading, error, send, retry, cancel, beginNewConversation, restoreConversation])
}
