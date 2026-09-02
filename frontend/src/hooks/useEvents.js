import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../api/api'
import { buildEventConversationGroups, filterEvents, filterEventsByView } from '../state/eventFeed'

const VIEW_STORAGE_KEY = 'a2a-events-view'

export default function useEvents() {
  const [events, setEvents] = useState([])
  const [runs, setRuns] = useState([])
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [type, setType] = useState('all')
  const [state, setState] = useState('all')
  const [query, setQuery] = useState('')
  const [view, setView] = useState(() => window.localStorage.getItem(VIEW_STORAGE_KEY) || 'summary')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [nextEvents, nextRuns, nextAgents] = await Promise.all([
        api.listEvents(), api.listRuns().catch(() => []), api.listAgents().catch(() => []),
      ])
      setEvents(nextEvents); setRuns(nextRuns); setAgents(nextAgents)
    }
    catch (cause) { setError(cause.message || String(cause)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { window.localStorage.setItem(VIEW_STORAGE_KEY, view) }, [view])
  const filteredEvents = useMemo(() => filterEvents(events, { type, state, query }), [events, type, state, query])
  const visibleEvents = useMemo(() => filterEventsByView(filteredEvents, view), [filteredEvents, view])
  const groups = useMemo(() => buildEventConversationGroups(filteredEvents, runs, agents), [filteredEvents, runs, agents])
  const stats = useMemo(() => ({
    total: events.length,
    completed: events.filter(event => event.state === 'completed').length,
    failed: events.filter(event => event.state === 'failed').length,
    multi: new Set(events.filter(event => event.conversation_type === 'multi').map(event => event.conversation_id)).size,
  }), [events])

  return { events, loading, error, load, type, setType, state, setState, query, setQuery, view, setView, visibleEvents, groups, stats }
}
