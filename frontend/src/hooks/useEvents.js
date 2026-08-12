import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../api/api'
import { filterEvents, filterEventsByView, groupEventsByConversation } from '../state/eventFeed'

const VIEW_STORAGE_KEY = 'a2a-events-view'

export default function useEvents() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [type, setType] = useState('all')
  const [state, setState] = useState('all')
  const [query, setQuery] = useState('')
  const [view, setView] = useState(() => window.localStorage.getItem(VIEW_STORAGE_KEY) || 'summary')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setEvents(await api.listEvents()) }
    catch (cause) { setError(cause.message || String(cause)) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { window.localStorage.setItem(VIEW_STORAGE_KEY, view) }, [view])
  const visibleEvents = useMemo(() => filterEvents(filterEventsByView(events, view), { type, state, query }), [events, view, type, state, query])
  const groups = useMemo(() => Object.entries(groupEventsByConversation(visibleEvents)), [visibleEvents])
  const stats = useMemo(() => ({
    total: events.length,
    completed: events.filter(event => event.state === 'completed').length,
    failed: events.filter(event => event.state === 'failed').length,
    multi: new Set(events.filter(event => event.conversation_type === 'multi').map(event => event.conversation_id)).size,
  }), [events])

  return { events, loading, error, load, type, setType, state, setState, query, setQuery, view, setView, visibleEvents, groups, stats }
}
