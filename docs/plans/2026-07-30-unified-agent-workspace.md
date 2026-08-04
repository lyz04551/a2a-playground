# Unified Agent Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the separate single-Agent and multi-Agent chat experiences with one polished Workspace supporting Direct and Auto execution through a shared Run API and event model.

**Architecture:** Introduce a versioned, append-only Run event envelope and a backend Run Service with Direct and Auto strategies. Migrate the React frontend onto one normalized reducer and stream client, then replace the two chat routes with a unified three-pane Workspace while keeping legacy endpoints available during migration.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy/SQLite, `a2a-sdk==0.3.25`, LangGraph, pytest, React 18, Ant Design 6, Vite 5, Node test runner.

---

## Working rules

- Work only inside `a2a-playground1`.
- Preserve the user's existing uncommitted changes.
- Use a dedicated `codex/` worktree or branch before implementation.
- Follow TDD: add one failing behavior, make it pass, then refactor.
- Do not remove the existing message or Host endpoints until the compatibility
  tests and unified Workspace pass.
- Do not add Team mode, workflow editing, authentication, or a new state library.
- Before each completion claim, use `@verification-before-completion`.

### Task 1: Define the versioned Run event contract

**Files:**

- Create: `backend/orchestration/__init__.py`
- Create: `backend/orchestration/events.py`
- Create: `tests/backend/test_run_events.py`

**Step 1: Write the failing event-model tests**

Test that:

```python
event = RunEvent.create(
    event_type=RunEventType.RUN_STARTED,
    run_id="run-1",
    conversation_id="conv-1",
    sequence=1,
    data={"mode": "direct"},
)
assert event.version == 1
assert event.type == "run.started"
assert event.sequence == 1
assert event.task_id is None
assert event.model_dump(mode="json")["timestamp"].endswith("Z")
```

Also verify that sequence values below `1` and unsupported event types are rejected.

**Step 2: Run the focused test and verify failure**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_run_events.py -q
```

Expected: FAIL because `backend.orchestration.events` does not exist.

**Step 3: Implement the minimal event contract**

Add a string enum containing:

```python
RUN_STARTED = "run.started"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"
RUN_CANCELLED = "run.cancelled"
HOST_PLANNING = "host.planning"
TASK_DELEGATED = "task.delegated"
TASK_STARTED = "task.started"
TASK_STATUS_CHANGED = "task.status_changed"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"
MESSAGE_DELTA = "message.delta"
MESSAGE_COMPLETED = "message.completed"
TOOL_CALLED = "tool.called"
TOOL_COMPLETED = "tool.completed"
APPROVAL_REQUIRED = "approval.required"
APPROVAL_DECIDED = "approval.decided"
ARTIFACT_CREATED = "artifact.created"
```

Implement `RunEvent` as a Pydantic model with `version`, `event_id`,
`sequence`, `run_id`, `conversation_id`, optional `task_id`, optional
`parent_task_id`, `type`, UTC timestamp, and `data`.

**Step 4: Run the test and verify success**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_run_events.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/orchestration tests/backend/test_run_events.py
git commit -m "feat: define unified run events"
```

### Task 2: Persist task hierarchy and ordered events

**Files:**

- Modify: `backend/persistence/models.py`
- Modify: `backend/persistence/repository.py`
- Create: `tests/backend/test_run_repository.py`

**Step 1: Write failing repository tests**

Create a temporary SQLite repository and verify:

```python
repo.create_task({
    "id": "task-root",
    "run_id": "run-1",
    "parent_task_id": None,
    "agent_id": "host",
    "status": "planning",
})
repo.create_task({
    "id": "task-child",
    "run_id": "run-1",
    "parent_task_id": "task-root",
    "agent_id": "k8s-ops",
    "status": "working",
})
assert repo.list_tasks("run-1")[1]["parent_task_id"] == "task-root"
```

Add two Run events and assert repository-assigned sequences are `[1, 2]`.
Attempt to add the same `event_id` twice and assert only one row exists.

**Step 2: Run the focused test and verify failure**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_run_repository.py -q
```

Expected: FAIL because task and ordered-event methods do not exist.

**Step 3: Add the schema and repository methods**

Add an `orchestration_tasks` table with:

- `id`
- `run_id`
- nullable `parent_task_id`
- `agent_id`
- `status`
- `data`

Add `sequence` to the stored event data without requiring a destructive SQLite
column migration. Implement:

- `create_task`
- `update_task`
- `list_tasks`
- `append_run_event`
- `list_run_events(after_sequence=0)`

Assign the next sequence inside one transaction. Treat a duplicate event ID as an
idempotent append.

**Step 4: Run persistence tests**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_run_repository.py tests/backend/test_persistence.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/persistence tests/backend/test_run_repository.py
git commit -m "feat: persist run task hierarchy"
```

### Task 3: Build Direct and Auto execution strategies

**Files:**

- Create: `backend/orchestration/commands.py`
- Create: `backend/orchestration/strategies.py`
- Create: `tests/backend/test_execution_strategies.py`
- Modify: `backend/host/langgraph/manager.py`

**Step 1: Write failing strategy tests**

Use fake async gateways and a fake Host manager.

Direct assertions:

- missing `target_agent_id` raises a stable validation error;
- one target produces `task.delegated`, streamed message/tool events, and
  `task.completed`;
- remote errors produce `task.failed`.

Auto assertions:

- the Host stream is normalized into the new envelope;
- two routing events create two child tasks under the Host root task;
- approval events retain the delegated task ID.

**Step 2: Run and verify failure**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_execution_strategies.py -q
```

Expected: FAIL because the strategy modules do not exist.

**Step 3: Implement `RunCommand`**

Use a Pydantic model:

```python
class RunCommand(BaseModel):
    conversation_id: str | None = None
    mode: Literal["direct", "auto"]
    target_agent_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)
```

Validate that Direct requires a target and Auto ignores an accidental target.

**Step 4: Implement the strategies**

Define an `ExecutionStrategy` protocol whose `execute` method yields normalized
domain events. Keep persistence out of both strategies.

- `DirectExecutionStrategy` resolves the selected Agent and streams through
  `A2AGateway`.
- `AutoExecutionStrategy` streams through `LangGraphHostManager`.
- Extract Host event normalization from endpoint code into the Auto strategy.

Do not add parallel APIs or Team configuration. Auto may naturally delegate more
than once through the existing Host graph.

**Step 5: Run strategy and existing gateway tests**

Run:

```bash
backend/.venv/bin/pytest \
  tests/backend/test_execution_strategies.py \
  tests/backend/test_a2a_gateway.py \
  tests/backend/test_single_agent_event_stream.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/orchestration backend/host/langgraph/manager.py tests/backend/test_execution_strategies.py
git commit -m "feat: add direct and auto run strategies"
```

### Task 4: Add the Run Service and unified API

**Files:**

- Create: `backend/orchestration/service.py`
- Create: `backend/api/__init__.py`
- Create: `backend/api/runs.py`
- Modify: `backend/main.py`
- Create: `tests/backend/test_run_service.py`
- Create: `tests/backend/test_runs_api.py`

**Step 1: Write failing Run Service tests**

Verify that the service:

- creates a conversation when none is supplied;
- creates one Run and a root task;
- persists every event before yielding it;
- saves the completed assistant message once;
- marks failures and preserves partial output;
- leaves a Run active when the client iterator is closed;
- returns persisted events after a supplied sequence cursor.

**Step 2: Run the service tests and verify failure**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_run_service.py -q
```

Expected: FAIL because `RunService` does not exist.

**Step 3: Implement `RunService`**

Give the service injected repository, registry/gateway, and Auto Host dependencies.
The service selects only `"direct"` or `"auto"`, owns ID creation and persistence,
and serializes each `RunEvent` to the SSE layer.

Do not let endpoint code accumulate message text or construct task records.

**Step 4: Write failing API tests**

Test:

```http
POST /api/runs/stream
POST /api/runs/get
POST /api/runs/list
POST /api/runs/events
POST /api/runs/cancel
POST /api/system/status
```

Assert the first stream event provides authoritative Run and conversation IDs.
Assert Direct without a target returns a structured `400`. Assert model status
returns `configured: true|false` and never returns the key.

**Step 5: Implement the routers**

Move the existing Run and approval endpoints into routers without changing their
wire format. Add the unified endpoints and include routers in `backend/main.py`.
Keep legacy endpoints operational.

Use one SSE formatter:

```python
def encode_sse(event: RunEvent) -> str:
    return f"data: {event.model_dump_json()}\\n\\n"
```

**Step 6: Run backend API tests**

Run:

```bash
backend/.venv/bin/pytest \
  tests/backend/test_run_service.py \
  tests/backend/test_runs_api.py \
  tests/backend/test_backend_import_mode.py -q
```

Expected: PASS.

**Step 7: Commit**

```bash
git add backend/api backend/orchestration backend/main.py tests/backend/test_run_service.py tests/backend/test_runs_api.py
git commit -m "feat: expose unified run API"
```

### Task 5: Create the shared frontend stream client and reducer

**Files:**

- Create: `frontend/src/api/runStream.js`
- Create: `frontend/src/api/runStream.test.js`
- Replace: `frontend/src/state/runEvents.js`
- Replace: `frontend/src/state/runEvents.test.js`
- Modify: `frontend/src/api/api.js`

**Step 1: Write failing parser tests**

Cover:

- SSE chunks split in the middle of UTF-8 and JSON boundaries;
- multiple events in one chunk;
- blank lines and comments;
- duplicate `event_id` values;
- non-2xx JSON responses;
- reconnect cursor propagation.

The parser result must be the exact versioned event envelope, not a component-specific
shape.

**Step 2: Run and verify failure**

Run:

```bash
npm --prefix frontend test
```

Expected: FAIL because `runStream.js` is absent or the reducer does not accept the
new event types.

**Step 3: Implement the parser and stream client**

Export:

```javascript
export function createSSEParser(onEvent) {}
export async function streamRun(command, handlers, options = {}) {}
```

Use `TextDecoder` with streaming enabled. Track `event_id` in a bounded Set and
reconnect with `after_sequence` only for retriable network interruption.

**Step 4: Implement normalized run state**

State contains:

```javascript
{
  run,
  tasksById,
  taskOrder,
  messages,
  approvals,
  artifacts,
  seenEventIds,
  lastSequence,
}
```

Handle every event in the design contract. Keep legacy normalization in one adapter
function until old pages are removed.

**Step 5: Run frontend tests**

Run:

```bash
npm --prefix frontend test
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/api frontend/src/state
git commit -m "feat: unify frontend run streaming"
```

### Task 6: Establish the visual system and shared Workspace components

**Files:**

- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/workspace.css`
- Create: `frontend/src/components/workspace/ModeSwitch.jsx`
- Create: `frontend/src/components/workspace/SystemStatus.jsx`
- Create: `frontend/src/components/workspace/MessageTimeline.jsx`
- Create: `frontend/src/components/workspace/ToolActivity.jsx`
- Create: `frontend/src/components/workspace/RunTracePanel.jsx`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/index.css`

**Step 1: Add pure component/state tests where practical**

Test mode transition rules as a pure helper:

```javascript
assert.equal(canChangeMode({ messageCount: 0 }), true)
assert.equal(canChangeMode({ messageCount: 1 }), false)
```

Test status mapping so offline Agent, missing model configuration, running,
approval-required, and failure states have distinct labels and icons.

**Step 2: Run tests and verify failure**

Run:

```bash
npm --prefix frontend test
```

Expected: FAIL because Workspace helpers do not exist.

**Step 3: Add design tokens**

Define semantic tokens for:

- page, surface, elevated surface, border, and text;
- primary, orchestration, approval, danger, and muted states;
- spacing `4/8/12/16/24/32/48`;
- radius `8/12/16`;
- focus ring and elevation;
- light and dark color schemes.

Move the multi-agent `--ops-*` variables into semantic tokens. Do not introduce a
second CSS framework.

**Step 4: Build presentational components**

Components receive normalized props and emit callbacks only. They must include:

- keyboard-visible focus;
- text plus icon for status;
- collapsed raw JSON details;
- empty, loading, error, approval, and artifact states;
- `prefers-reduced-motion` handling.

**Step 5: Run tests and build**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: PASS and Vite build completes without warnings introduced by this task.

**Step 6: Commit**

```bash
git add frontend/src/styles frontend/src/components/workspace frontend/src/App.jsx frontend/src/main.jsx frontend/src/index.css
git commit -m "feat: add agent workspace design system"
```

### Task 7: Implement the unified Workspace page

**Files:**

- Create: `frontend/src/pages/WorkspacePage.jsx`
- Create: `frontend/src/hooks/useRunStream.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/api/api.js`
- Modify: `frontend/src/pages/AgentsPage.jsx`

**Step 1: Write failing hook/helper tests**

Extract and test:

- Direct send is disabled until an online Agent is selected.
- Auto send is disabled when the model is unconfigured or no Agents are online.
- a mode change with existing messages requests a new conversation;
- restoring a conversation restores mode, target Agent, Run, approvals, and trace;
- a duplicate stream event cannot duplicate text or a tool call.

**Step 2: Run tests and verify failure**

Run:

```bash
npm --prefix frontend test
```

Expected: FAIL because the Workspace state helpers are missing.

**Step 3: Implement `useRunStream`**

The hook owns:

- normalized reducer state;
- stream start and reconnection;
- cancel and retry actions;
- conversation restoration;
- approval refresh;
- cleanup without implicit Run cancellation.

**Step 4: Build `WorkspacePage`**

Implement the approved three-region layout:

- conversations on the left;
- messages and composer in the center;
- execution trace on the right.

Use Direct/Auto segmented selection. Show the Agent selector only in Direct mode.
Auto mode shows Host identity and online Agent count. A shortcut from Agents opens a
new Direct conversation with the Agent preselected.

On tablet widths, replace the side regions with drawers.

**Step 5: Switch routes**

Change navigation to:

- `/workspace`
- `/agents`
- `/runs`
- `/settings`

Redirect `/chat`, `/chat/:agentId`, and `/multi` into Workspace with compatible query
parameters. Do not delete the old page files in this task.

**Step 6: Run frontend verification**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/src/pages/WorkspacePage.jsx frontend/src/hooks frontend/src/App.jsx frontend/src/api/api.js frontend/src/pages/AgentsPage.jsx
git commit -m "feat: add unified agent workspace"
```

### Task 8: Add Runs and Settings diagnostics

**Files:**

- Create: `frontend/src/pages/RunsPage.jsx`
- Create: `frontend/src/pages/SettingsPage.jsx`
- Modify: `frontend/src/pages/EventsPage.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/api/api.js`

**Step 1: Add failing presentation helper tests**

Test filtering and summaries for:

- Direct versus Auto Runs;
- completed, failed, active, and approval-required Runs;
- model unconfigured;
- Agent reachable but model unavailable;
- Agent offline.

**Step 2: Run and verify failure**

Run:

```bash
npm --prefix frontend test
```

Expected: FAIL because Runs and Settings helpers do not exist.

**Step 3: Implement Runs**

Replace the top-level Events experience with:

- Run list and status filters;
- duration, mode, target/delegated Agents, and task count;
- full task tree;
- messages, artifacts, approvals, and raw event drawer.

Keep `EventsPage.jsx` as a temporary redirect or wrapper.

**Step 4: Implement Settings diagnostics**

Display:

- Host model configured/unconfigured;
- provider and model name without secrets;
- backend readiness;
- each Agent's HTTP, Agent Card, and model readiness;
- actionable remediation text.

Do not add an API-key editing form in this scope.

**Step 5: Run frontend tests and build**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/pages frontend/src/App.jsx frontend/src/api/api.js
git commit -m "feat: add run history and diagnostics"
```

### Task 9: Compatibility, integration, and cleanup

**Files:**

- Modify: `tests/backend/test_single_agent_event_stream.py`
- Modify: `tests/backend/test_a2a_gateway.py`
- Create: `tests/backend/test_legacy_api_compatibility.py`
- Modify: `README.md`
- Modify: `guide.md`
- Modify: `DESIGN.md`
- Delete after verification: `frontend/src/pages/ChatPage.jsx`
- Delete after verification: `frontend/src/pages/MultiAgentPage.jsx`

**Step 1: Add failing compatibility tests**

Verify legacy Direct and Host endpoints still:

- accept their current payloads;
- produce their existing event types;
- persist messages exactly once;
- delegate through the same A2A Gateway;
- do not bypass approval policy.

**Step 2: Run and verify the tests**

Run:

```bash
backend/.venv/bin/pytest tests/backend/test_legacy_api_compatibility.py -q
```

Expected: initially FAIL for any contract broken during extraction.

**Step 3: Add thin compatibility adapters**

Adapt legacy request/event shapes at the API boundary. Do not duplicate execution
logic or SSE parsing. Mark legacy routes as deprecated in API documentation.

**Step 4: Remove obsolete frontend pages**

After route redirects, frontend tests, and production build pass, delete the unused
Chat and Multi-Agent page implementations and any CSS reachable only from them.
Keep reusable approval, artifact, badge, and trace components.

**Step 5: Update documentation**

Document:

- Direct and Auto behavior;
- unified startup and environment configuration;
- model versus Agent readiness;
- new Run endpoints and event envelope;
- approval resume semantics;
- legacy endpoint deprecation.

Correct conflicting port and JSON/SQLite statements while updating the docs.

**Step 6: Run the complete verification suite**

Run:

```bash
backend/.venv/bin/pytest -q
npm --prefix frontend test
npm --prefix frontend run build
docker compose config
```

Expected: all tests pass, production frontend builds, and Compose configuration is
valid.

If Docker Desktop is running, additionally run:

```bash
docker compose up --build -d
curl -fsS -X POST http://127.0.0.1:8050/api/system/status \
  -H 'Content-Type: application/json' -d '{}'
docker compose down
```

Expected: the status endpoint succeeds and no secret value appears in the response.

**Step 7: Perform manual acceptance checks**

- Start a Direct conversation with K8s Ops.
- Start an Auto conversation that consults Ops and Security.
- Trigger a write requiring approval and refresh before approving.
- Confirm the same Run resumes after approval.
- Disconnect and reconnect the browser during streaming.
- Confirm duplicate text and tool cards do not appear.
- Check desktop and tablet layouts using keyboard navigation.
- Confirm model-unconfigured and Agent-offline states are visually distinct.

**Step 8: Commit**

```bash
git add backend frontend tests README.md guide.md DESIGN.md
git commit -m "refactor: complete unified agent workspace migration"
```

## Final review checkpoint

Use `@verification-before-completion` and review:

- no Team mode or saved-team configuration was introduced;
- Direct and Auto share the same Run Service and frontend stream reducer;
- legacy API compatibility is intentional and documented;
- no API key or raw internal exception reaches the browser;
- user-owned changes outside this plan remain untouched;
- `git status --short` contains no unexpected staged files.
