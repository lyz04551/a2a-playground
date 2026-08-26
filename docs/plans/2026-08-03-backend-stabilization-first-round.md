# Backend Stabilization First-Round Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix backend import correctness and improve outbound-network security, API access control, SQLite write behavior, A2A error reporting, and Run cancellation without changing frontend payload contracts.

**Architecture:** Keep the current FastAPI, synchronous SQLAlchemy repository, and A2A layers, but introduce small boundary modules for settings/security and typed transport failures. Use `backend.*` as the sole package namespace and preserve current uncommitted event-feed work in `backend/main.py`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, SQLite, HTTPX, pytest/AnyIO.

---

### Task 1: Canonical backend package imports

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/database.py`
- Modify: `backend/a2a_gateway.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/orchestration/strategies.py`
- Modify: `backend/persistence/repository.py`
- Modify: `backend/host/adk/manager.py`
- Modify: `backend/host/langgraph/manager.py`
- Modify: `backend/host/langgraph/agent.py`
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Test: `tests/backend/test_backend_import_mode.py`

1. Extend the import regression test to assert the service, strategies, repository, and API router share the exact same `RunEvent` class.
2. Run `python -m pytest tests/backend/test_backend_import_mode.py tests/backend/test_execution_strategies.py tests/backend/test_run_repository.py -q` and verify the existing class-identity failures.
3. Replace internal top-level and fallback imports with canonical `backend.*` imports.
4. Change local and Docker startup targets to `backend.main:app`, with repository-root Python path and Docker build context.
5. Re-run the focused tests and `python -m pytest tests/backend -q`.

### Task 2: Agent URL validation and CORS/authentication settings

**Files:**
- Create: `backend/security.py`
- Create: `backend/settings.py`
- Modify: `backend/a2a_client.py`
- Modify: `backend/main.py`
- Modify: `docker-compose.yml`
- Test: `tests/backend/test_security.py`
- Test: `tests/backend/test_runs_api.py`

1. Write tests that reject unsupported schemes, credentials, localhost, loopback/link-local/private/reserved IPs, and DNS answers containing blocked addresses; test the explicit private-network override.
2. Write API tests proving authentication is optional when unset, enforced with constant-time Bearer comparison when configured, and excluded for `/api/ping`; test explicit CORS origins.
3. Run the new tests and confirm they fail because the settings and validator do not exist.
4. Implement `validate_agent_url`, resolving all host addresses and rejecting the complete request if any resolved address is unsafe.
5. Call validation before card fetching, health checks, legacy sends, and SDK sends.
6. Add settings parsers, an HTTP authentication middleware, and explicit development CORS defaults. Configure Compose with private-network opt-in and its frontend origin.
7. Re-run focused security/API tests.

### Task 3: Atomic SQLite message writes and indexes

**Files:**
- Modify: `backend/persistence/models.py`
- Modify: `backend/persistence/repository.py`
- Test: `tests/backend/test_persistence.py`
- Test: `tests/backend/test_run_repository.py`

1. Add tests proving one message transaction increments `message_count` and `updated_at`, and concurrent inserts do not lose increments.
2. Add schema inspection tests for common lookup indexes.
3. Run the focused tests and verify failures.
4. Add `updated_at` and `message_count` columns to new schemas, idempotently upgrade existing databases, and perform insert plus counter increment in one transaction.
5. Enable foreign keys, WAL, and configurable busy timeout on connection.
6. Add indexes for messages/events by conversation, runs by conversation/status, tasks by run/status, and approvals by run/status.
7. Re-run persistence tests.

### Task 4: Typed A2A failures

**Files:**
- Modify: `backend/a2a_client.py`
- Modify: `backend/main.py`
- Modify: `backend/orchestration/strategies.py`
- Test: `tests/backend/test_a2a_client.py`
- Test: `tests/backend/test_execution_strategies.py`

1. Add tests for timeout, transport error, protocol incompatibility fallback, and failure information reaching API/Run events.
2. Run focused tests and verify they fail for ambiguous `{"text": "", "state": "failed"}` behavior.
3. Add `A2AClientError` subclasses carrying a safe public message and diagnostic cause.
4. Restrict legacy fallback to explicit incompatible-method/status/content-type cases and raise typed errors otherwise.
5. Translate typed failures at API and execution strategy boundaries without returning internal exception strings.
6. Re-run focused tests.

### Task 5: Active Run cancellation and stream cleanup

**Files:**
- Modify: `backend/orchestration/service.py`
- Modify: `backend/api/runs.py`
- Test: `tests/backend/test_run_service.py`
- Test: `tests/backend/test_runs_api.py`

1. Add an AnyIO regression test with a blocking fake strategy, cancel the Run, and assert execution exits, durable status is `cancelled`, one cancellation event exists, and the active registry is cleaned.
2. Add a stream-disconnection test proving generator cancellation triggers cleanup without marking the Run completed.
3. Run focused tests and verify failures.
4. Register the current execution task by Run ID after durable Run creation, clean it in `finally`, and cancel it only when cancellation originates from another task.
5. Preserve idempotent durable cancellation and explicitly avoid claiming remote cancellation.
6. Re-run focused Run tests.

### Task 6: Full verification and documentation alignment

**Files:**
- Modify: `README.md`
- Modify: `guide.md`

1. Update startup commands and document `PLAYGROUND_API_KEY`, `PLAYGROUND_CORS_ORIGINS`, `PLAYGROUND_ALLOW_PRIVATE_AGENTS`, and SQLite timeout settings.
2. Run `python -m pytest tests/backend -q`.
3. Run `python -m pytest -q`.
4. Run `docker compose config` and build the backend image if the Docker daemon is available.
5. Run `git diff --check` and inspect the final diff for accidental edits to user-owned changes.
