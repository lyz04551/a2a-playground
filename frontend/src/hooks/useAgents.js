import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../api/api'

const HEALTH_REFRESH_MS = 30_000

export default function useAgents() {
  const [agents, setAgents] = useState([])
  const [healthMap, setHealthMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [healthLoading, setHealthLoading] = useState(false)
  const [error, setError] = useState('')
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setAgents(await api.listAgents())
    } catch (cause) {
      setError(cause.message || String(cause))
    } finally {
      setLoading(false)
    }
  }, [])

  const checkHealth = useCallback(async () => {
    setHealthLoading(true)
    try {
      setHealthMap(await api.checkAgentsHealth())
    } catch (cause) {
      setError(cause.message || String(cause))
    } finally {
      setHealthLoading(false)
    }
  }, [])

  const remove = useCallback(async agentId => {
    await api.deleteAgent(agentId)
    await load()
  }, [load])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!agents.length) return undefined
    checkHealth()
    timerRef.current = window.setInterval(checkHealth, HEALTH_REFRESH_MS)
    return () => window.clearInterval(timerRef.current)
  }, [agents.length, checkHealth])

  return { agents, healthMap, loading, healthLoading, error, clearError: () => setError(''), load, checkHealth, remove }
}
