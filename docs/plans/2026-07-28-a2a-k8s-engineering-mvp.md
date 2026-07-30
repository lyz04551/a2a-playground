# A2A Kubernetes Engineering MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a polished, extensible A2A Kubernetes multi-agent MVP with a shared runtime, three independent agents, deterministic tool policy and approval, durable Host orchestration, SQLite tracking, and Docker Compose startup.

**Architecture:** Keep the Playground backend as a modular management and persistence application. Run Ops, Orchestrator, and Security as independent `a2a-sdk` servers that install a shared local runtime package. The LangGraph Host dynamically delegates through `a2a-sdk`; SQLite records runs rather than imposing a fixed workflow.

**Tech Stack:** Python 3.11, FastAPI/Starlette, `a2a-sdk`, LangGraph, LangChain, MCP SSE client, SQLAlchemy/SQLite, pytest, React 18, Ant Design, Vite, Docker Compose.

---

## Execution Rules

- Work in `/Users/liyangzhong/Documents/GitHub/a2a-samples/a2a-playground1`.
- Standardize all services on the project's current `a2a-sdk==0.3.25`; do not
  upgrade the SDK or redesign against a newer protocol/API during this MVP.
- Preserve existing single-agent endpoints and UI behavior.
- For every behavior change, write and run the failing test before production code.
- Do not call the live Kubernetes MCP from automated tests.
- Do not execute write tools against a real Kubernetes cluster during verification.
- Commit only files under `a2a-playground1`; do not stage unrelated parent repository changes.

### Task 1: Establish test harness and shared runtime package

**Files:**
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `agents/shared-runtime/pyproject.toml`
- Create: `agents/shared-runtime/a2a_runtime/__init__.py`
- Create: `agents/shared-runtime/a2a_runtime/config.py`
- Test: `tests/runtime/test_config.py`

**Step 1: Write the failing configuration test**

Test that an agent configuration:

- has a stable ID, name, description, port, skills, and policy;
- loads environment substitutions for public URL and MCP URL;
- rejects an empty stable ID.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/runtime/test_config.py -v
```

Expected: collection fails because `a2a_runtime.config` does not exist.

**Step 3: Implement the minimal package**

Add Pydantic configuration models:

```python
class ToolPolicyConfig(BaseModel):
    allow: list[str] = []
    deny: list[str] = []
    approval_required: list[str] = []

class AgentRuntimeConfig(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str
    description: str
    port: int
    public_url: str
    mcp_url: str
    skills: list[dict]
    tool_policy: ToolPolicyConfig
```

Provide a YAML loader with `${ENV_NAME}` substitution.

**Step 4: Verify GREEN**

Run the Task 1 pytest command. Expected: all Task 1 tests pass.

**Step 5: Commit**

```bash
git add a2a-playground1/pytest.ini a2a-playground1/tests a2a-playground1/agents/shared-runtime
git commit -m "feat: add shared A2A runtime configuration"
```

### Task 2: Implement deterministic MCP tool policy

**Files:**
- Create: `agents/shared-runtime/a2a_runtime/tool_policy.py`
- Create: `agents/shared-runtime/a2a_runtime/models.py`
- Test: `tests/runtime/test_tool_policy.py`

**Step 1: Write failing policy tests**

Cover:

- read-only glob allow;
- explicit deny overriding allow;
- write tool returning `approval_required`;
- global dangerous-tool deny;
- exact canonical argument digest;
- stable digest independent of JSON key order;
- approval mismatch when any argument changes.

The desired API is:

```python
decision = policy.classify("patch_k8s_resource", arguments)
assert decision.action == PolicyAction.APPROVAL_REQUIRED
pending = PendingAction.from_call(...)
assert pending.matches_approval(tool_name, same_arguments)
```

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/runtime/test_tool_policy.py -v
```

Expected: fail because policy classes are missing.

**Step 3: Implement minimal policy**

Use `fnmatch` for patterns. Precedence is:

```text
global deny → agent deny → approval required → allow → deny by default
```

Canonicalize arguments with sorted compact JSON and SHA-256. Never persist an
approval token containing raw credentials.

**Step 4: Verify GREEN**

Run Task 2 tests and the entire `tests/runtime` directory.

**Step 5: Commit**

```bash
git add a2a-playground1/agents/shared-runtime/a2a_runtime a2a-playground1/tests/runtime
git commit -m "feat: enforce MCP tool policy and approval digests"
```

### Task 3: Extract MCP client and LangChain tool adapter

**Files:**
- Create: `agents/shared-runtime/a2a_runtime/mcp_client.py`
- Create: `agents/shared-runtime/a2a_runtime/tool_adapter.py`
- Test: `tests/runtime/test_tool_adapter.py`
- Test: `tests/runtime/test_mcp_client.py`

**Step 1: Write failing adapter tests**

Test nested JSON Schema types, arrays, required fields, optional defaults, and
descriptions. Test that policy filtering omits denied tools and wraps
approval-required tools without calling the fake MCP session.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/runtime/test_tool_adapter.py tests/runtime/test_mcp_client.py -v
```

Expected: missing modules.

**Step 3: Implement minimal client and adapter**

Move the existing SSE lifecycle behavior into `K8sMCPClient`. Inject the session
factory so tests use a fake session. Convert MCP schemas into Pydantic models and
LangChain `StructuredTool` instances. Enforce policy in the execution wrapper.

An approval-required wrapper raises a typed `ApprovalRequired` carrying a
`PendingAction`; it does not call MCP.

**Step 4: Verify GREEN**

Run Task 3 tests and all runtime tests.

**Step 5: Commit**

```bash
git add a2a-playground1/agents/shared-runtime a2a-playground1/tests/runtime
git commit -m "refactor: extract reusable MCP client and tool adapter"
```

### Task 4: Build reusable LangGraph agent and A2A executor

**Files:**
- Create: `agents/shared-runtime/a2a_runtime/agent.py`
- Create: `agents/shared-runtime/a2a_runtime/executor.py`
- Create: `agents/shared-runtime/a2a_runtime/server.py`
- Create: `agents/shared-runtime/a2a_runtime/streaming.py`
- Test: `tests/runtime/test_executor.py`
- Test: `tests/runtime/test_server.py`

**Step 1: Write failing A2A contract tests**

With a fake graph and fake event queue, verify:

- a new A2A task is enqueued;
- intermediate text becomes `working`;
- structured results become named artifacts;
- `ApprovalRequired` becomes `input_required` plus `pending_action` artifact;
- approved continuation uses the same task and context;
- denied tools fail safely;
- cancellation calls the runtime cancellation hook.

Validate the generated Agent Card stable name, skills, URL, modes, and streaming
capability.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/runtime/test_executor.py tests/runtime/test_server.py -v
```

Expected: missing runtime implementation.

**Step 3: Implement minimal runtime**

Create a reusable ReAct agent around injected model and tools. Normalize graph
events into typed runtime events. Implement a generic `AgentExecutor` and an
`A2AStarletteApplication` factory using `a2a-sdk`.

**Step 4: Verify GREEN**

Run all runtime tests.

**Step 5: Commit**

```bash
git add a2a-playground1/agents/shared-runtime a2a-playground1/tests/runtime
git commit -m "feat: add reusable LangGraph A2A agent runtime"
```

### Task 5: Convert Ops and Orchestrator and add Security Agent

**Files:**
- Create: `agents/k8s-ops/agent.yaml`
- Create: `agents/k8s-ops/prompt.md`
- Create: `agents/k8s-ops/main.py`
- Create: `agents/k8s-ops/Dockerfile`
- Create: `agents/k8s-ops/requirements.txt`
- Create: `agents/k8s-orchestrator/agent.yaml`
- Create: `agents/k8s-orchestrator/prompt.md`
- Create: `agents/k8s-orchestrator/main.py`
- Create: `agents/k8s-orchestrator/Dockerfile`
- Create: `agents/k8s-orchestrator/requirements.txt`
- Create: `agents/k8s-security/agent.yaml`
- Create: `agents/k8s-security/prompt.md`
- Create: `agents/k8s-security/main.py`
- Create: `agents/k8s-security/Dockerfile`
- Create: `agents/k8s-security/requirements.txt`
- Test: `tests/agents/test_agent_configs.py`
- Test: `tests/agents/test_agent_cards.py`

**Step 1: Write failing agent tests**

Assert:

- all three configurations load;
- IDs and public URLs are unique;
- all three cards validate through `a2a.types.AgentCard`;
- Ops and Security expose no mutation tool;
- Orchestrator mutations require approval;
- global dangerous tools remain denied;
- Security output schema supports structured findings.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/agents -v
```

Expected: new agent directories/configurations do not exist.

**Step 3: Implement agents**

Create thin entry points using the shared runtime. Preserve compatibility wrappers
at current `k8s-ops` and `k8s-orchestrator` paths or update documented startup
commands so existing direct chat registration continues to work.

Security scans generic resource YAML and emits:

```json
{
  "summary": "...",
  "severity": "high",
  "findings": [],
  "evidence": [],
  "remediations": []
}
```

**Step 4: Verify GREEN**

Run agent and runtime tests. Fetch each locally constructed Agent Card in a test.

**Step 5: Commit**

```bash
git add a2a-playground1/agents a2a-playground1/k8s-ops a2a-playground1/k8s-orchestrator a2a-playground1/tests/agents
git commit -m "feat: add three policy-isolated A2A Kubernetes agents"
```

### Task 6: Replace JSON persistence with SQLite and one-time import

**Files:**
- Create: `backend/persistence/__init__.py`
- Create: `backend/persistence/models.py`
- Create: `backend/persistence/repository.py`
- Create: `backend/persistence/migrate_json.py`
- Modify: `backend/database.py`
- Modify: `backend/requirements.txt`
- Test: `tests/backend/test_persistence.py`
- Test: `tests/backend/test_json_migration.py`

**Step 1: Write failing persistence tests**

Using a temporary SQLite file, verify:

- foreign keys and transactions;
- agent CRUD by stable ID and duplicate display names;
- conversation/message compatibility;
- orchestration run, child task binding, approval, artifact, and event persistence;
- approval decision idempotency;
- JSON files import exactly once and remain unchanged.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/backend/test_persistence.py tests/backend/test_json_migration.py -v
```

Expected: persistence package missing.

**Step 3: Implement minimal SQLite repository**

Use SQLAlchemy 2.x with a session factory. Keep `backend/database.py` as a
compatibility façade so current endpoints need incremental rather than wholesale
changes.

**Step 4: Verify GREEN**

Run backend persistence tests and runtime tests.

**Step 5: Commit**

```bash
git add a2a-playground1/backend a2a-playground1/tests/backend
git commit -m "feat: add SQLite persistence and JSON import"
```

### Task 7: Implement stable A2A registry and context continuation

**Files:**
- Create: `backend/registry/__init__.py`
- Create: `backend/registry/service.py`
- Create: `backend/a2a_gateway.py`
- Refactor: `backend/a2a_client.py`
- Test: `tests/backend/test_registry.py`
- Test: `tests/backend/test_a2a_gateway.py`

**Step 1: Write failing registry/gateway tests**

Verify:

- duplicate names do not overwrite stable IDs;
- card refresh updates capabilities but preserves ID;
- healthy candidates are filtered by skill and risk;
- first delegation creates a remote context;
- second delegation to the same agent/run reuses context;
- client resources close on unregister and shutdown;
- task, status, artifacts, and input-required events normalize correctly.

**Step 2: Verify RED**

Run the two Task 7 test modules. Expected: missing services.

**Step 3: Implement services**

Inject A2A clients in tests. In production use `ClientFactory`, `ClientConfig`, and
SDK `Message`. Persist remote task bindings after every delegation.

**Step 4: Verify GREEN**

Run all backend tests.

**Step 5: Commit**

```bash
git add a2a-playground1/backend a2a-playground1/tests/backend
git commit -m "feat: add stable A2A registry and context continuation"
```

### Task 8: Upgrade Host dynamic orchestration and approval continuation

**Files:**
- Refactor: `backend/host/langgraph/agent.py`
- Refactor: `backend/host/langgraph/manager.py`
- Create: `backend/orchestration/__init__.py`
- Create: `backend/orchestration/service.py`
- Create: `backend/approvals/__init__.py`
- Create: `backend/approvals/service.py`
- Modify: `backend/main.py`
- Test: `tests/backend/test_host_tools.py`
- Test: `tests/backend/test_orchestration.py`
- Test: `tests/backend/test_approval_api.py`

**Step 1: Write failing Host tests**

Use a fake A2A gateway and deterministic fake model to verify:

- Host delegates by stable ID;
- Host may ask the user instead of delegating;
- child artifacts return to Host;
- input-required creates a durable approval;
- approve continues the exact remote task/context;
- reject returns control to Host without child execution;
- run events survive stream reconnect;
- Host has no Kubernetes MCP tool.

**Step 2: Verify RED**

Run Task 8 tests. Expected: missing orchestration and approval behavior.

**Step 3: Implement minimal orchestration**

Keep the Host LLM in control. `OrchestrationService` records decisions and exposes
Host A2A tools; it does not prescribe a DAG. Add compatible APIs for run queries and
approval decisions. Normalize SSE events with IDs.

**Step 4: Verify GREEN**

Run all backend tests.

**Step 5: Commit**

```bash
git add a2a-playground1/backend a2a-playground1/tests/backend
git commit -m "feat: add durable Host orchestration and approvals"
```

### Task 9: Build Conversation + Workflow frontend

**Files:**
- Modify: `frontend/src/api/api.js`
- Modify: `frontend/src/pages/MultiAgentPage.jsx`
- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/pages/AgentsPage.jsx`
- Modify: `frontend/src/pages/EventsPage.jsx`
- Modify: `frontend/src/index.css`
- Create: `frontend/src/components/OrchestrationTrace.jsx`
- Create: `frontend/src/components/ApprovalCard.jsx`
- Create: `frontend/src/components/ArtifactCard.jsx`
- Create: `frontend/src/components/AgentBadge.jsx`
- Create: `frontend/src/state/runEvents.js`
- Add or modify: `frontend/package.json`
- Test: `frontend/src/state/runEvents.test.js`
- Test: `frontend/src/components/ApprovalCard.test.jsx`
- Test: `frontend/src/components/OrchestrationTrace.test.jsx`

**Step 1: Write failing reducer/component tests**

Cover:

- normalized SSE event reduction;
- run/step ordering;
- reconnect without duplicate events;
- approval detail rendering;
- approve and reject API calls;
- artifact rendering;
- single-chat input-required rendering.

**Step 2: Verify RED**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: tests fail because reducer and components are missing.

**Step 3: Implement the selected layout**

Create the dark operations workspace:

- main conversation column;
- right trace column;
- responsive trace drawer;
- cyan/green active states and amber approval cards;
- agent identity, skill, and health display;
- durable run reload.

Preserve all existing routes.

**Step 4: Verify GREEN**

Run frontend tests, then:

```bash
cd frontend && npm run build
```

Expected: tests pass and Vite build exits 0.

**Step 5: Visual verification**

Start frontend/backend with fake or local agents, capture the Agents, Single Chat,
Multi-Agent, approval, and Events screens, and inspect desktop and narrow layouts.

**Step 6: Commit**

```bash
git add a2a-playground1/frontend
git commit -m "feat: add conversation and orchestration workspace"
```

### Task 10: Docker Compose and operational documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `README.md`
- Modify: `DESIGN.md`
- Create: `.env.example`
- Create: `.gitignore`
- Test: `tests/smoke/test_compose_config.py`

**Step 1: Write failing Compose configuration test**

Parse Compose and assert services, health checks, stable URLs, persistent SQLite
volume, shared environment values, and dependency health conditions.

**Step 2: Verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest tests/smoke/test_compose_config.py -v
```

Expected: missing Agent services and health checks.

**Step 3: Implement Compose and docs**

Define `frontend`, `backend`, `host-agent`, `k8s-ops`, `k8s-orchestrator`, and
`k8s-security`. Use service DNS names in Agent Cards. Document direct chat,
multi-agent chat, approvals, security defaults, and JSON migration.

Ignore `.superpowers/`, local SQLite files, virtual environments, environment
secrets, and generated frontend assets.

**Step 4: Verify Compose**

Run:

```bash
docker compose config
```

Expected: exit 0 with six resolved services.

**Step 5: Commit**

```bash
git add a2a-playground1/docker-compose.yml a2a-playground1/backend/Dockerfile a2a-playground1/frontend/Dockerfile a2a-playground1/README.md a2a-playground1/DESIGN.md a2a-playground1/.env.example a2a-playground1/.gitignore a2a-playground1/tests/smoke
git commit -m "build: compose complete A2A Kubernetes MVP"
```

### Task 11: Full verification and smoke demonstration

**Files:**
- Fix only files implicated by verification failures.

**Step 1: Run backend/runtime/agent suite**

```bash
backend/.venv/bin/python -m pytest -v
```

Expected: zero failures.

**Step 2: Run frontend suite and build**

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

Expected: zero test failures and build exit 0.

**Step 3: Run static checks**

```bash
backend/.venv/bin/python -m compileall backend agents
docker compose config
```

Expected: both commands exit 0.

**Step 4: Start isolated services**

```bash
docker compose up --build -d
docker compose ps
```

Expected: all defined services become healthy. If the external MCP or LLM is
unavailable, Agent Card discovery and health must still work while task execution
returns a clear dependency error.

**Step 5: Run non-destructive smoke flow**

Verify:

1. discover all Agent Cards;
2. direct Ops read-only chat;
3. direct Security assessment;
4. direct Orchestrator request stops at approval without executing;
5. Host delegates via A2A and records a run;
6. approval rejection resumes Host without mutation;
7. frontend shows the trace and approval.

Do not approve a real write against the live MCP during verification.

**Step 6: Inspect repository state**

```bash
git status --short
git diff --check
```

Expected: no whitespace errors and no unrelated files staged.

**Step 7: Final commit if verification fixes were required**

```bash
git add <only verified MVP files>
git commit -m "test: verify A2A Kubernetes MVP"
```
