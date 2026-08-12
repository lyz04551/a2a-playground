import test from 'node:test'
import assert from 'node:assert/strict'
import { createSSEParser, streamRun } from './runStream.js'

const encoder = new TextEncoder()

function envelope(eventId, sequence, type = 'message.delta', data = {}) {
  return {
    version: 1,
    event_id: eventId,
    sequence,
    run_id: 'run-1',
    conversation_id: 'conversation-1',
    task_id: 'task-1',
    parent_task_id: null,
    type,
    timestamp: '2026-07-30T12:00:00Z',
    data,
  }
}

function response(chunks, { status = 200, bodyError } = {}) {
  let index = 0
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return { success: false, error: 'Invalid run command' } },
    body: {
      getReader() {
        return {
          async read() {
            if (bodyError && index === 1) throw bodyError
            if (index >= chunks.length) return { done: true }
            return { done: false, value: encoder.encode(chunks[index++]) }
          },
        }
      },
    },
  }
}

test('parser preserves a UTF-8 envelope split across byte and JSON boundaries', () => {
  const events = []
  const parser = createSSEParser(event => events.push(event))
  const serialized = `data: ${JSON.stringify(envelope('evt-1', 1, 'message.delta', { content: '你好' }))}\n\n`
  const bytes = encoder.encode(serialized)
  const split = bytes.indexOf(0xe5) + 1

  parser.push(bytes.slice(0, split))
  parser.push(bytes.slice(split, bytes.length - 2))
  parser.push(bytes.slice(bytes.length - 2))
  parser.finish()

  assert.deepEqual(events, [envelope('evt-1', 1, 'message.delta', { content: '你好' })])
})

test('parser emits multiple data events while ignoring comments and blank lines', () => {
  const events = []
  const parser = createSSEParser(event => events.push(event))
  parser.push(encoder.encode(`: keepalive\n\ndata: ${JSON.stringify(envelope('evt-1', 1))}\n\ndata: ${JSON.stringify(envelope('evt-2', 2, 'run.completed'))}\n\n`))
  parser.finish()

  assert.deepEqual(events.map(event => event.event_id), ['evt-1', 'evt-2'])
  assert.equal(events[1].type, 'run.completed')
})

test('stream client delivers each event id only once within its bounded dedupe window', async () => {
  const received = []
  await streamRun(
    { mode: 'auto', message: 'inspect' },
    { onEvent: event => received.push(event) },
    {
      fetch: async () => response([
        `data: ${JSON.stringify(envelope('evt-1', 1))}\n\n`,
        `data: ${JSON.stringify(envelope('evt-1', 1))}\n\n`,
      ]),
    },
  )

  assert.deepEqual(received.map(event => event.event_id), ['evt-1'])
})

test('stream client reports a JSON error response without attempting a reconnect', async () => {
  const errors = []
  let attempts = 0
  await assert.rejects(
    streamRun(
      { mode: 'auto', message: 'inspect' },
      { onError: error => errors.push(error) },
      { fetch: async () => { attempts += 1; return response([], { status: 422 }) } },
    ),
    /Invalid run command/,
  )

  assert.equal(attempts, 1)
  assert.equal(errors[0].status, 422)
  assert.equal(errors[0].message, 'Invalid run command')
})

test('stream client reconnects network interruptions with the last received sequence cursor', async () => {
  const bodies = []
  const received = []
  let attempts = 0
  const first = `data: ${JSON.stringify(envelope('evt-1', 7))}\n\n`
  const second = `data: ${JSON.stringify(envelope('evt-2', 8, 'run.completed'))}\n\n`

  await streamRun(
    { mode: 'auto', message: 'inspect' },
    { onEvent: event => received.push(event) },
    {
      fetch: async (_url, init) => {
        bodies.push(JSON.parse(init.body))
        attempts += 1
        return attempts === 1
          ? response([first, ''], { bodyError: new TypeError('connection reset') })
          : response([second])
      },
      maxReconnects: 1,
    },
  )

  assert.deepEqual(received.map(event => event.sequence), [7, 8])
  assert.deepEqual(bodies, [
    { mode: 'auto', message: 'inspect' },
    { mode: 'auto', message: 'inspect', run_id: 'run-1', after_sequence: 7 },
  ])
})

test('stream client does not reconnect an aborted request', async () => {
  let attempts = 0
  const abort = new DOMException('The operation was aborted', 'AbortError')

  await assert.rejects(
    streamRun(
      { mode: 'auto', message: 'inspect' },
      {},
      { fetch: async () => { attempts += 1; throw abort }, maxReconnects: 3 },
    ),
    error => error === abort,
  )

  assert.equal(attempts, 1)
})

test('stream client propagates an event handler exception without reconnecting', async () => {
  let attempts = 0
  const handlerError = new Error('render failed')

  await assert.rejects(
    streamRun(
      { mode: 'auto', message: 'inspect' },
      { onEvent: () => { throw handlerError } },
      {
        fetch: async () => {
          attempts += 1
          return response([`data: ${JSON.stringify(envelope('evt-1', 1))}\n\n`])
        },
        maxReconnects: 3,
      },
    ),
    error => error === handlerError,
  )

  assert.equal(attempts, 1)
})

test('stream client propagates a completion handler exception without reconnecting', async () => {
  let attempts = 0
  const handlerError = new Error('completion failed')

  await assert.rejects(
    streamRun(
      { mode: 'auto', message: 'inspect' },
      { onComplete: () => { throw handlerError } },
      {
        fetch: async () => {
          attempts += 1
          return response([])
        },
        maxReconnects: 3,
      },
    ),
    error => error === handlerError,
  )

  assert.equal(attempts, 1)
})
