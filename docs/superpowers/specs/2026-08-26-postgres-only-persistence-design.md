# Postgres-only persistence design

## Goal

Replace the backend's SQLite persistence and every agent's in-memory LangGraph checkpointer with Postgres-backed persistence. Docker Compose becomes the canonical local runtime. The new deployment starts with empty Postgres databases; existing SQLite and legacy JSON data are not migrated.

The change must preserve the current backend API, Direct conversations, Auto orchestration, approval flow, event stream, and frontend rendering behavior.

## Scope

Included:

- Move backend business data to Postgres.
- Remove SQLite runtime support, SQLite configuration, SQLite-specific SQL, and the legacy JSON-to-SQLite importer.
- Add a Postgres service to Docker Compose with durable local storage and a health check.
- Use a Postgres LangGraph checkpointer in every shared-runtime Agent.
- Persist Agent conversation state across Agent process restarts when the same LangGraph `thread_id` is reused.
- Add automated repository, API, Compose, and browser regression coverage.
- Document startup, configuration, reset, and test commands.

Excluded:

- Migrating existing `playground-local.db` or legacy JSON rows.
- Making LangGraph checkpoint tables part of the backend business API.
- Reworking the frontend user experience.
- Replacing the existing custom approval protocol with LangGraph `interrupt` in this change.

## Architecture

One Postgres container hosts two logical databases:

- `playground`: backend-owned business tables.
- `langgraph`: LangGraph-owned checkpoint tables.

The backend accesses only `playground`. Agents access only `langgraph`. They use different connection URLs and credentials where practical. Backend code must not query or mutate LangGraph's internal tables.

The stable identity chain remains:

```text
conversation_id -> A2A context_id -> LangGraph thread_id
```

Each Agent retains its existing Agent-qualified context ID, so multiple Agents participating in one Auto conversation do not share graph state accidentally.

## Backend persistence

Rename the repository to a database-neutral `DatabaseRepository`, but support Postgres only at runtime. Construct its SQLAlchemy engine from the required `DATABASE_URL` environment variable. Absence of the variable, an unsupported URL scheme, or an unavailable database is a startup error with a clear message.

Reuse the existing SQLAlchemy Core table definitions and public repository methods so API and orchestration callers do not change. Replace SQLite-only behavior as follows:

- Use PostgreSQL `INSERT ... ON CONFLICT` for Agent upserts.
- Remove SQLite PRAGMA, WAL, busy-timeout, file-path, and directory creation logic.
- Replace SQLite JSON functions used for message counters and timestamps with a transactionally locked read-update-write operation. This keeps the stored JSON envelope consistent with the normalized columns without adding Postgres-specific JSON expressions throughout the repository.
- Use PostgreSQL-compatible indexes and constraints.
- Create and upgrade the schema through Alembic migrations instead of runtime `ALTER TABLE` inspection.

Application startup runs an explicit migration command or a small migration entrypoint before serving traffic. Schema migration failure prevents the backend from becoming ready.

## Agent checkpoints

The shared Agent runtime uses `AsyncPostgresSaver`, because graph execution uses asynchronous streaming. `AGENT_CHECKPOINT_DATABASE_URL` is required in the Docker Compose runtime.

The checkpointer is opened once during Agent initialization, retained for the lifetime of the compiled graph, and closed during Agent shutdown. Its schema setup is performed as a deployment/startup migration step and is safe to run before multiple Agents start.

Calls that inspect graph state use the asynchronous API, including `aget_state`, so no synchronous checkpointer methods are invoked from the async stream path.

If Postgres is unavailable, the Agent reports degraded readiness and does not silently fall back to memory. This prevents conversations from appearing persistent while actually being process-local.

The existing `_pending_by_context` approval cache remains outside the checkpoint scope. Backend approval records remain authoritative. Approval survival across an Agent restart is not promised unless the current A2A resume protocol can reconstruct the pending action from persisted backend data; that behavior will be covered explicitly in tests and reported if further protocol work is required.

## Docker Compose and configuration

Docker Compose adds one durable Postgres service with a named volume and health check. Backend and Agent services depend on the healthy Postgres service.

Required URLs:

```text
DATABASE_URL=postgresql+psycopg://...@postgres:5432/playground
AGENT_CHECKPOINT_DATABASE_URL=postgresql://...@postgres:5432/langgraph
```

Credentials are sourced from environment variables and example development defaults. Production secrets are not committed. Resetting the named Postgres volume intentionally deletes all local backend and checkpoint data and must be documented as destructive.

## Failure and consistency behavior

- Backend database failure: startup/readiness fails; requests are not served against an in-memory substitute.
- Agent checkpoint failure: Agent readiness is degraded and requests return a dependency error without losing the stable context ID.
- Transaction failure: the whole repository mutation rolls back.
- Duplicate event or approval writes: existing unique keys and idempotent repository behavior remain enforced by Postgres constraints.
- Concurrent message writes: the conversation row is locked while its embedded message count and update timestamp are changed.
- Database reset: the system starts empty and the three configured Agents are registered through the normal bootstrap or registration path.

## Verification strategy

### Repository and API tests

Tests run against a disposable Postgres database and cover:

- schema migration from an empty database;
- Agent registration and upsert;
- conversation, message, event, Run, orchestration task, remote binding, approval, and artifact operations;
- pagination, ordering, constraints, cascading behavior, and transaction rollback;
- backend restart with previously written data still available;
- clear startup failure when `DATABASE_URL` is missing or unreachable.

### Agent checkpoint tests

- Two runtime instances using the same `thread_id` and Postgres database see the same prior graph state.
- Different Agent-qualified thread IDs remain isolated.
- Agent restart preserves multi-turn context.
- Async state inspection and shutdown complete without resource warnings.
- Missing or unreachable checkpoint Postgres produces degraded readiness rather than a memory fallback.

### Compose smoke tests

- Compose configuration contains Postgres, health checks, durable volume, both database URLs, and dependency ordering.
- The full stack reaches healthy status from an empty volume.
- Restarting backend and Agent containers does not remove persisted conversations or checkpoints.

### Browser regression

Run a real browser against the Compose stack:

1. Verify three Agents are registered and visible.
2. Open a Direct conversation with each Agent, send a deterministic read-only prompt, and wait for a completed reply.
3. Confirm user messages, Agent messages, status indicators, and tool activity render without page errors.
4. Start an Auto conversation that coordinates the three Agents and confirm Host decisions, Agent task cards, event activity, and final output render.
5. Reload the page and confirm the conversation history remains visible.
6. Restart backend and Agent services, reopen the same conversations, and confirm backend history remains visible and an Agent follow-up retains its prior LangGraph context.

Tests that require an LLM or Kubernetes MCP endpoint use explicitly configured test dependencies. Repository and UI rendering tests must not rely on an uncontrolled production cluster mutation.

## Rollout

1. Add Postgres dependencies, schema migrations, and disposable test database support.
2. Convert the backend repository and pass its integration tests.
3. Add Compose Postgres wiring and validate backend persistence across restart.
4. Convert the shared Agent runtime to `AsyncPostgresSaver` and validate checkpoint recovery.
5. Run API, runtime, Compose, and browser regressions.
6. Remove SQLite code, SQLite tests, obsolete data-path settings, and legacy migration startup behavior only after the Postgres path passes.

## Acceptance criteria

- Docker Compose starts only after Postgres is healthy.
- The backend and Agents do not use SQLite or `MemorySaver` in production code.
- A clean deployment creates all required schemas and registers the expected three Agents.
- Direct and Auto conversations complete and render correctly in the frontend.
- Backend history and LangGraph conversation state survive relevant process/container restarts.
- Existing non-database regression suites remain green.
- No existing SQLite or JSON data is imported into the new Postgres databases.
