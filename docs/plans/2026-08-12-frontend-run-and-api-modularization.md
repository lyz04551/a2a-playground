# Frontend Run Convergence and API Modularization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the active UI use one Run stream path, reduce initial bundle size, and move cohesive API domains out of `backend/main.py` without changing contracts.

**Architecture:** Preserve `runStream.js`, `useRunStream`, and the normalized reducer as the active streaming stack. Lazy-load routed pages, remove unreachable legacy page/stream modules, then introduce dependency-injected FastAPI router factories for CRUD domains.

**Tech Stack:** React 18, React Router 6, Vite 5, Node test runner, FastAPI, Pydantic 2, pytest.

---

### Task 1: Prove and remove the legacy frontend stream surface

**Files:**
- Modify: `frontend/src/api/api.js`
- Delete: `frontend/src/pages/ChatPage.jsx`
- Delete: `frontend/src/pages/MultiAgentPage.jsx`
- Test: `frontend/src/api/apiSurface.test.js`

1. Add a test asserting the public API module exposes `streamRun` and does not expose the four legacy stream functions.
2. Run the focused test and confirm it fails on the legacy exports.
3. Remove legacy stream clients and unreachable page implementations.
4. Run the frontend test suite.

### Task 2: Lazy-load routes and create stable chunks

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/vite.config.js`
- Test: `frontend/src/appRoutes.test.js`

1. Add a source-level regression test proving routed pages use lazy imports rather than eager imports.
2. Run it and confirm the eager route implementation fails.
3. Add `React.lazy`, a shared `Suspense` fallback, and stable vendor chunks.
4. Run tests and the production build; compare chunk output with the baseline.

### Task 3: Extract Agent API routes

**Files:**
- Create: `backend/api/agents.py`
- Modify: `backend/main.py`
- Test: `tests/backend/test_agent_routes.py`

1. Add contract tests against a router created with fake dependencies.
2. Run them and confirm the router factory is missing.
3. Move Agent list/fetch/register/get/delete/health routes behind a router factory.
4. Include the router from `main.py` and run Agent/security tests.

### Task 4: Extract conversation CRUD, message query, and event routes

**Files:**
- Create: `backend/api/conversations.py`
- Modify: `backend/main.py`
- Test: `tests/backend/test_conversation_routes.py`

1. Add route contract tests for CRUD, message listing, and event queries.
2. Run them and confirm the router factory is missing.
3. Move CRUD/query endpoints while preserving models and envelopes. Keep legacy
   message-send streaming in `main.py` until its backend transport is retired.
4. Run focused and complete backend suites.

### Task 5: Verify and document

**Files:**
- Modify: `README.md`

1. Align the architecture description with SQLite and the versioned Run stream.
2. Run `npm test`, `npm run build`, and `backend/.venv/bin/python -m pytest -q`.
3. Run `git diff --check` and inspect only phase-owned changes.
