# Host Model Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a console page that safely displays and updates the model used only by new Host Agent runs.

**Architecture:** PostgreSQL stores one optional runtime override. A backend service resolves it over environment defaults and exposes redacted get/update/reset APIs. Host model creation reads the resolver when constructing models; the React page edits it through the existing API client.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, React, Ant Design, Node test runner, pytest.

---

### Task 1: Persist and resolve Host model configuration

**Files:**
- Modify: `backend/persistence/models.py`
- Modify: `backend/persistence/repository.py`
- Create: `backend/persistence/migrations/versions/20260908_0002_host_model_config.py`
- Create: `backend/model_config.py`
- Test: `tests/backend/test_model_config.py`

Write failing tests for environment fallback, override precedence, secret redaction/retention, reset, validation, and encryption-key failure. Add the singleton table, repository operations, validation, encryption, and resolver. Run the focused tests and commit.

### Task 2: Expose APIs and apply configuration to Host model creation

**Files:**
- Modify: `backend/api/runs.py`
- Modify: `backend/main.py`
- Modify: `backend/host/langgraph/agent.py`
- Modify: `backend/host/langgraph/manager.py`
- Test: `tests/backend/test_model_config.py`

Write failing API and model-factory tests. Inject the configuration service, add get/update/reset endpoints, and make Host model creation resolve the latest configuration for new calls without changing child Agents. Run focused tests and commit.

### Task 3: Add Model Settings page

**Files:**
- Modify: `frontend/src/api/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/shell/AppShell.jsx`
- Modify: `frontend/src/components/shell/CommandPalette.jsx`
- Create: `frontend/src/pages/ModelSettingsPage.jsx`
- Create: `frontend/src/state/modelConfig.js`
- Create: `frontend/src/state/modelConfig.test.js`
- Create: `frontend/src/styles/model-settings.css`
- Modify: `frontend/src/main.jsx`

Write failing payload/navigation tests. Add the route below Events, redacted status, editable form, save/reset states, and responsive styles. Run frontend tests and commit.

### Task 4: Verify and publish

Run focused backend tests, the full frontend suite, production build, and `git diff --check`. Push the resulting commits to `main` only after all checks pass.
