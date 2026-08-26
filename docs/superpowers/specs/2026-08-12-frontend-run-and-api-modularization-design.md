# Frontend Run Convergence and API Modularization Design

## Goal

Converge the active frontend on the versioned Run event protocol, reduce the initial
JavaScript bundle, and extract backend route domains from `backend/main.py` without
changing public API paths or persisted data.

## Scope

This phase makes three bounded changes:

1. Keep `/api/runs/stream` and `useRunStream` as the only streaming path used by the
   routed application. Remove unreachable legacy chat pages and their private SSE
   clients after proving that no active route imports them.
2. Lazy-load routed pages and define stable React/Ant Design vendor chunks. Loading
   failures remain visible through a shared route fallback.
3. Extract Agent and conversation/message/event endpoints from `backend/main.py`
   into FastAPI routers. Existing URLs, request bodies, response envelopes, database
   calls, bootstrap behavior, and legacy Host endpoints remain compatible.

Authentication, PostgreSQL migration, event-schema changes, distributed Run workers,
and removal of backend legacy Host endpoints are deferred.

## Frontend design

`App.jsx` owns only shell composition and route declarations. Each real page is loaded
through `React.lazy` under one `Suspense` boundary. Redirect-only legacy URLs remain,
but the old `ChatPage` and `MultiAgentPage` implementations are no longer part of the
module graph.

`api/runStream.js` remains the sole versioned SSE transport. `useRunStream` remains the
UI integration boundary, and `runEvents.js` remains the normalized state reducer. The
legacy callback-style streaming functions are removed with their unreachable callers;
ordinary JSON request helpers stay in `api.js`.

## Backend design

Route extraction is dependency-explicit. Router factories receive the existing
repository facade and outbound Agent functions rather than creating new global service
objects. This keeps tests replaceable and avoids changing startup order. `main.py`
configures the app, constructs existing services, includes routers, and retains only
Host/compatibility endpoints not covered by this phase.

The first extraction targets cohesive low-risk CRUD domains. Run and approval routes
already live in `backend/api/runs.py` and are not redesigned.

## Compatibility and failure handling

- All existing `/api/*` paths and `ApiResponse` envelopes stay unchanged.
- Lazy route loading uses a visible loading state; runtime errors continue through the
  existing application error behavior.
- Run reconnect, deduplication, cancellation, and replay semantics are unchanged.
- Existing user worktree changes are preserved; changes are limited to named files.

## Testing

Tests are written before behavior changes. Frontend tests verify route modules are lazy
and the active API surface contains no legacy stream clients. Backend regression tests
exercise extracted routes through FastAPI and verify the same request/response contract.
Completion requires the full Python suite, frontend suite, production build, and
`git diff --check` to pass.
