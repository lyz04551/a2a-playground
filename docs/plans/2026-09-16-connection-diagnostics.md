# Connection Diagnostics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an on-demand diagnostics card that independently proves Host DeepSeek inference, child-Agent Qwen inference, and MCP tool discovery.

**Architecture:** Each child Agent exposes a read-only diagnostics endpoint backed by direct model invocation and MCP `list_tools`, without entering its ReAct graph. The backend runs its own Host-model probe, calls every registered Agent diagnostics endpoint concurrently, and exposes one stable aggregate API consumed by the Model Settings page.

**Tech Stack:** FastAPI, Starlette, httpx, LangChain `ChatOpenAI`, React, Ant Design, Node test runner, pytest.

---

### Task 1: Add child-Agent probes

**Files:**
- Modify: `agents/shared-runtime/a2a_runtime/agent.py`
- Modify: `agents/shared-runtime/a2a_runtime/server.py`
- Test: `tests/runtime/test_mcp_client.py`

1. Write failing tests for independent model success/failure and MCP tool-count probes.
2. Add a bounded direct model probe with hidden thinking disabled and no tools.
3. Add a bounded MCP `list_tools` probe.
4. Expose both results from `POST /health/diagnostics` without secrets or full response text.
5. Run focused runtime tests.

### Task 2: Add backend aggregation

**Files:**
- Create: `backend/diagnostics.py`
- Create: `backend/api/diagnostics.py`
- Modify: `backend/main.py`
- Test: `tests/backend/test_diagnostics.py`

1. Write failing tests for Host probe success/failure and concurrent Agent aggregation.
2. Invoke the currently resolved Host model with a short non-streaming request and strict timeout.
3. Call each registered Agent diagnostics endpoint concurrently; represent unsupported endpoints separately from offline Agents.
4. Add `POST /api/diagnostics/connections` and register its router.
5. Run focused backend tests.

### Task 3: Add the diagnostics card

**Files:**
- Modify: `frontend/src/api/api.js`
- Create: `frontend/src/state/connectionDiagnostics.js`
- Create: `frontend/src/state/connectionDiagnostics.test.js`
- Create: `frontend/src/components/ConnectionDiagnostics.jsx`
- Modify: `frontend/src/pages/ModelSettingsPage.jsx`
- Modify: `frontend/src/styles/model-settings.css`

1. Write a failing state-mapping test for healthy, partial, failed, unsupported, and testing results.
2. Add the aggregate diagnostics API client.
3. Render an explicit “Test all connections” card beneath model settings.
4. Show independent Host model, Agent model, and MCP status, latency, tool count, and bounded errors.
5. Run frontend tests and production build.

### Task 4: End-to-end verification

1. Restart is left to the user as previously requested; use the currently running services only if they reload automatically.
2. Verify the backend response contains no API keys or complete model output.
3. In a browser, click the diagnostics button and verify each dependency renders independently and the page remains responsive.
4. Run all relevant test suites, review the diff, and commit the implementation.
