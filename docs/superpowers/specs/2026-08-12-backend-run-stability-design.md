# Backend Run Stability Design

## Goal

Keep SQLite efficient as Run history grows, avoid continuous SSE polling, and leave
durable Runs in an honest state after backend restarts.

## Compatibility

- Existing SQLite databases are upgraded in place with nullable event columns and a
  deterministic backfill from validated Run envelopes.
- Existing list requests continue returning arrays. Pagination is opt-in through
  `page` and `page_size`, returning `{items, page, page_size, total, has_more}`.
- SQLite remains the replay source of truth. In-process notifications only wake waiting
  SSE connections and are never required for correctness.
- Restart recovery never re-executes remote work. `running` and planning/execution
  variants become `interrupted`; `approval_required` and terminal Runs remain unchanged.

## Event storage

The events table gains `run_id`, `sequence`, and `created_at`. Run writes populate these
columns transactionally. Startup backfills verified legacy Run envelopes and creates a
unique `(run_id, sequence)` index plus conversation/time and event-type/time indexes.
Legacy non-Run events use their payload timestamp for `created_at` when available.

## SSE notification

`RunService` owns a per-Run generation counter and `asyncio.Condition`. Persisting a Run
event schedules a notification. Reconnect streams replay all rows after their cursor,
inspect durable terminal state, and otherwise wait on the condition with a bounded
heartbeat timeout. The timeout keeps connections/proxies alive without querying SQLite
ten times per second.

## Restart recovery

The application startup hook calls `RunService.recover_interrupted_runs()`. Each active
Run is updated to `interrupted`, non-terminal tasks are updated likewise, and one durable
`run.failed` envelope with `reason=backend_restarted` records why execution stopped.

## Pagination

Repository pagination applies SQL `LIMIT/OFFSET` and count queries. Conversation filters
are applied in SQL where entity columns exist. Event-feed filtering that depends on
derived presentation data remains after loading the requested database page.
