# Backend Stabilization — First-Round Design

## Goal

Improve backend correctness, security, and concurrency behavior without changing
the frontend wire contract or replacing SQLite. Preserve the user's current
uncommitted event-feed and LangGraph changes.

## Scope

This round includes five bounded changes:

1. Make `backend` the only Python package namespace and remove dual import paths.
2. Validate outbound Agent URLs and add configurable API authentication and CORS.
3. Make message insertion and conversation counters atomic, add SQLite operational
   settings, and index common lookup fields.
4. Preserve actionable upstream A2A failures instead of converting them into
   ambiguous empty responses.
5. Make Run cancellation propagate to locally active execution tasks and handle
   stream disconnection cleanly where the current architecture permits.

Large route-module extraction, PostgreSQL migration, and removal of legacy APIs are
explicitly deferred. They would broaden the change and overlap heavily with current
work in `backend/main.py`.

## Design

### Package imports

All internal imports use the canonical `backend.*` namespace. The supported local
entry point becomes `python -m uvicorn backend.main:app`; Docker uses the same app
target from the repository parent. A regression test imports modules in both the
test and application paths and verifies that `RunEvent` has one class identity.

### URL and API security

Agent addresses pass through one validator before any network request. It accepts
only HTTP(S), requires a hostname, rejects embedded credentials, and rejects
loopback, link-local, multicast, unspecified, reserved, and private resolved IPs by
default. An explicit environment switch permits private Agent networks for the
existing Docker Compose topology. Redirects remain disabled.

Authentication is opt-in for local compatibility: when `PLAYGROUND_API_KEY` is
configured, all `/api/*` routes except health require `Authorization: Bearer ...`.
CORS origins come from `PLAYGROUND_CORS_ORIGINS`; the development default remains
the two local frontend origins rather than `*`.

### Persistence

SQLite connections enable foreign keys, WAL, and a configurable busy timeout.
Message insert, conversation `message_count` increment, and `updated_at` update run
in one transaction. Lookup indexes cover conversation messages/events, run status,
run tasks, and approvals. Existing JSON payloads remain the compatibility source for
API responses; no destructive schema migration is introduced.

### A2A errors and cancellation

The A2A client raises typed transport/protocol errors after narrowly defined legacy
fallback conditions. API boundaries translate these errors into stable error
responses while logs keep diagnostic context.

`RunService` tracks active execution tasks in process. Cancellation updates durable
state first, then cancels the active local task. Generator cleanup removes task
registrations. This cannot guarantee remote cancellation until the remote A2A
servers expose a compatible cancel operation, so the limitation is explicit and no
false remote-cancel acknowledgement is emitted.

## Compatibility and rollout

- Existing frontend request and SSE payload shapes remain unchanged.
- Docker Compose enables private Agent URLs and supplies explicit CORS origins.
- API authentication stays disabled unless an API key is configured.
- Existing SQLite databases gain indexes through idempotent metadata creation.
- Startup and test commands use the canonical package import path.

## Testing

Work proceeds test-first in independent slices:

1. Reproduce and eliminate duplicate module identities.
2. Cover rejected URL classes and the Docker private-network override.
3. Cover authentication enabled/disabled behavior and CORS configuration.
4. Verify atomic message counters under repeated and concurrent writes.
5. Verify typed upstream failures and active Run cancellation cleanup.
6. Run the complete backend suite, then the complete project test suite.

Success means the current seven backend failures are fixed, new security and
concurrency regression tests pass, and no frontend API contract changes are needed.
