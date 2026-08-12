const DEFAULT_DEDUPE_LIMIT = 1000

function dispatchRecord(record, onEvent) {
  const data = record.data.join('\n')
  if (!data) return
  let event
  try {
    event = JSON.parse(data)
  } catch {
    // A malformed SSE payload must not prevent later valid envelopes arriving.
    return
  }
  onEvent(event)
}

export function createSSEParser(onEvent) {
  const decoder = new TextDecoder()
  let buffer = ''
  let record = { data: [] }

  function consumeLine(line) {
    if (line === '') {
      dispatchRecord(record, onEvent)
      record = { data: [] }
      return
    }
    if (line.startsWith(':')) return
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    let value = separator === -1 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') record.data.push(value)
  }

  function consume(text) {
    buffer += text
    while (true) {
      const match = /\r\n|\r|\n/.exec(buffer)
      if (!match) return
      const line = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      consumeLine(line)
    }
  }

  return {
    push(chunk) {
      if (typeof chunk === 'string') consume(chunk)
      else consume(decoder.decode(chunk, { stream: true }))
    },
    finish() {
      consume(decoder.decode())
      if (buffer) consumeLine(buffer)
      if (record.data.length) dispatchRecord(record, onEvent)
      buffer = ''
      record = { data: [] }
    },
  }
}

async function responseError(response) {
  let payload
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  const message = payload?.error || payload?.message || `HTTP ${response.status}`
  const error = new Error(message)
  error.status = response.status
  error.payload = payload
  return error
}

function boundedRemember(ids, eventId, limit) {
  if (!eventId || ids.has(eventId)) return false
  ids.add(eventId)
  if (ids.size > limit) ids.delete(ids.values().next().value)
  return true
}

function isAbortError(error) {
  return error?.name === 'AbortError' || error?.code === 'ABORT_ERR'
}

function isRetriableNetworkInterruption(error) {
  return !isAbortError(error) && (
    error instanceof TypeError || error?.name === 'NetworkError'
  )
}

export async function streamRun(command, handlers = {}, options = {}) {
  const fetchImpl = options.fetch || globalThis.fetch
  if (!fetchImpl) throw new Error('Fetch is not available')
  const endpoint = options.endpoint || '/api/runs/stream'
  const maxReconnects = options.maxReconnects ?? 1
  const dedupeLimit = options.dedupeLimit ?? DEFAULT_DEDUPE_LIMIT
  const seenEventIds = new Set()
  let lastSequence = 0
  let runId = ''
  let reconnects = 0

  connection: while (true) {
    const body = reconnects === 0
      ? command
      : { ...command, run_id: runId, after_sequence: lastSequence }
    let response
    try {
      response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: options.signal,
      })
    } catch (error) {
      if (!isRetriableNetworkInterruption(error) || reconnects >= maxReconnects) {
        handlers.onError?.(error)
        throw error
      }
      reconnects += 1
      handlers.onReconnect?.({ attempt: reconnects, afterSequence: lastSequence, error })
      continue
    }

    if (!response.ok) {
      const error = await responseError(response)
      handlers.onError?.(error)
      throw error
    }
    if (!response.body) {
      const error = new Error('Response did not include a stream body')
      handlers.onError?.(error)
      throw error
    }

    const parser = createSSEParser(event => {
      if (!boundedRemember(seenEventIds, event?.event_id, dedupeLimit)) return
      if (event?.run_id) runId = event.run_id
      if (Number.isFinite(event.sequence)) lastSequence = Math.max(lastSequence, event.sequence)
      handlers.onEvent?.(event)
    })
    const reader = response.body.getReader()
    while (true) {
      let chunk
      try {
        chunk = await reader.read()
      } catch (error) {
        if (!isRetriableNetworkInterruption(error) || reconnects >= maxReconnects) {
          handlers.onError?.(error)
          throw error
        }
        reconnects += 1
        handlers.onReconnect?.({ attempt: reconnects, afterSequence: lastSequence, error })
        continue connection
      }
      if (chunk.done) break
      parser.push(chunk.value)
    }
    parser.finish()
    handlers.onComplete?.({ lastSequence })
    return { lastSequence }
  }
}
