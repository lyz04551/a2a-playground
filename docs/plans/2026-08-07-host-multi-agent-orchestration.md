# Host Multi-Agent Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Auto mode from single-Agent routing to a bounded, observable orchestrator that plans, schedules, retries, replans, and synthesizes work across multiple registered Agents while preserving Direct mode and approval safety.

**Architecture:** Add framework-neutral plan contracts and a deterministic engine under `backend/host/orchestration/`. LangGraph and ADK adapters provide model decisions; the engine validates dependency graphs, schedules bounded concurrent A2A calls, passes selected predecessor context, and emits normalized events consumed by the existing Run service. Capability and frontend changes remain additive for backward compatibility.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, asyncio, LangGraph, Google ADK, A2A SDK, SQLite, pytest/AnyIO, React 18, Vitest.

**References:** `docs/superpowers/specs/2026-08-07-host-multi-agent-orchestration-design.md` and the matching `-zh.md`.

**Rules:** Use @test-driven-development for every behavior and @verification-before-completion at handoff. Before editing any existing file, inspect its current diff and preserve user changes. Direct mode must remain unchanged. No path may bypass approval. Commit each task separately.

---

### Task 1: Define and validate orchestration plans

**Files:**
- Create: `backend/host/orchestration/__init__.py`
- Create: `backend/host/orchestration/models.py`
- Create: `backend/host/orchestration/validation.py`
- Create: `tests/backend/test_host_plan_validation.py`

**Step 1: Write failing tests**

Cover valid one-node and dependency plans, duplicate IDs, missing dependencies, cycles, more than six nodes, unknown Agents, empty completion criteria, invalid attempt counts, and write work assigned to a read-only Agent.

Use this public shape:

```python
plan = HostPlan(
    summary="diagnose then remediate",
    tasks=[
        PlannedTask(
            id="diagnose",
            agent_id="k8s-ops",
            objective="find root cause",
            completion_criteria=["root cause has evidence"],
            risk="read",
            max_attempts=2,
        ),
        PlannedTask(
            id="remediate",
            agent_id="k8s-orchestrator",
            objective="prepare remediation",
            depends_on=["diagnose"],
            completion_criteria=["safe change is specified"],
            risk="write",
            max_attempts=2,
        ),
    ],
)
assert validate_plan(plan, agents) is plan
```

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_plan_validation.py`

Expected: collection fails because the package does not exist.

**Step 3: Implement minimal contracts**

Define Pydantic `PlannedTask` and `HostPlan`. Limit task IDs to 80 characters, tasks to 1–6, `risk` to `read|write`, and attempts to 1–2. Implement deterministic checks for IDs, references, cycles, Agent existence, and read-only compatibility.

Also define framework-neutral `DelegationResult`, `Evaluation`, and a `DecisionPort` protocol with `create_plan`, `evaluate`, and `synthesize`.

**Step 4: Verify GREEN**

Run: `pytest -q tests/backend/test_host_plan_validation.py tests/backend/test_host_tools.py`

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/host/orchestration tests/backend/test_host_plan_validation.py
git commit -m "feat: define host orchestration contracts"
```

---

### Task 2: Normalize and rank Agent capabilities

**Files:**
- Modify: `backend/registry/service.py`
- Modify: `backend/models.py`
- Modify: `agents/shared-runtime/a2a_runtime/models.py`
- Modify: `agents/shared-runtime/a2a_runtime/config.py`
- Modify: `agents/k8s-ops/agent.yaml`
- Modify: `agents/k8s-security/agent.yaml`
- Modify: `agents/k8s-orchestrator/agent.yaml`
- Modify: `tests/backend/test_registry.py`
- Modify: `tests/agents/test_agent_configs.py`

**Step 1: Inspect current diffs**

Run: `git diff -- backend/models.py backend/registry/service.py agents/shared-runtime/a2a_runtime/models.py agents/shared-runtime/a2a_runtime/config.py agents/k8s-ops/agent.yaml agents/k8s-security/agent.yaml agents/k8s-orchestrator/agent.yaml`

**Step 2: Write failing tests**

Require conservative legacy defaults, stable IDs, `read_only`, `risk_level`, `limitations`, `priority`, tags and examples. Prove exact skill matches rank before tag-only matches, offline Agents are excluded, write work excludes read-only Agents, and ties end with stable Agent ID ordering.

**Step 3: Verify RED**

Run: `pytest -q tests/backend/test_registry.py tests/agents/test_agent_configs.py`

Expected: new capability and ranking assertions fail.

**Step 4: Implement**

Add backward-compatible fields with safe defaults. Implement `capability_profile(agent_id)` and `rank_candidates(skill, tags, risk, exclude)`. Sort by exact skill match, overlapping tag count, priority, then stable ID. Retain `find_candidates` as a compatibility wrapper. Extend YAML metadata without changing tool policies.

**Step 5: Verify**

Run: `pytest -q tests/backend/test_registry.py tests/agents/test_agent_configs.py tests/agents/test_agent_cards.py tests/runtime/test_config.py tests/runtime/test_tool_policy.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/registry backend/models.py agents/shared-runtime/a2a_runtime agents/k8s-ops/agent.yaml agents/k8s-security/agent.yaml agents/k8s-orchestrator/agent.yaml tests/backend/test_registry.py tests/agents/test_agent_configs.py
git commit -m "feat: normalize agent capability profiles"
```

---

### Task 3: Build dependency scheduling and bounded context

**Files:**
- Create: `backend/host/orchestration/context.py`
- Create: `backend/host/orchestration/engine.py`
- Create: `tests/backend/test_host_orchestration_engine.py`

**Step 1: Write failing scheduler tests**

Inject a fake `DecisionPort` and recording delegate. Prove:
- one-node plans call one Agent;
- two independent tasks overlap using `asyncio.Event` barriers;
- active calls never exceed three;
- dependent tasks wait for predecessors;
- dependent prompts contain labeled relevant findings;
- unrelated branch output is absent;
- invalid plans fail before delegation;
- emitted events cover plan, context, delegation, start, evaluation, completion, synthesis, text, and done.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py`

Expected: engine imports fail.

**Step 3: Implement context building**

Create prompts with objective, completion criteria, relevant original request, constraints, labeled predecessor findings, and a findings/evidence/uncertainty/next-steps response contract. Never pass raw history or unrelated output.

**Step 4: Implement minimal engine**

Implement `HostOrchestrationEngine.stream(request, run_id)` as an async iterator. Validate plans, find ready nodes, run them through `asyncio.create_task` guarded by `Semaphore(3)`, and emit deterministic mappings compatible with the current Host stream plus additive lifecycle events.

**Step 5: Verify GREEN**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py tests/backend/test_execution_strategies.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/host/orchestration tests/backend/test_host_orchestration_engine.py
git commit -m "feat: schedule host plan dependencies"
```

---

### Task 4: Add evaluation, retry, replacement, approval blocking, and partial results

**Files:**
- Modify: `backend/host/orchestration/models.py`
- Modify: `backend/host/orchestration/context.py`
- Modify: `backend/host/orchestration/engine.py`
- Modify: `tests/backend/test_host_orchestration_engine.py`

**Step 1: Write failing recovery tests**

Separately prove transient failure retries once; insufficient output retries with the evaluator reason; exhausted attempts request a compatible replacement excluding tried Agents; replacement preserves risk and dependencies; no replacement retains independent successes; failed predecessors block only descendants; approval pauses only its branch; synthesis sees every terminal state; and one Agent never exceeds `max_attempts`.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py -k "retry or insufficient or replacement or partial or blocked or approval"`

Expected: assertions fail after first result.

**Step 3: Implement bounded execution state**

Track logical task ID separately from attempts and replacement Agent IDs. Retry only while attempts remain. After exhaustion, select at most one compatible replacement. Never modify objective, risk, dependency IDs, or approval requirements.

Emit `task.retry_scheduled`, `host.plan_revised`, and `task.evaluated` with safe reasons and counts.

**Step 4: Implement blocking and partial synthesis**

Continue independent branches. Mark descendants blocked without calling them when a required predecessor cannot complete. Preserve `approval_required` results. Synthesize whenever a truthful partial answer exists; fail the root only when planning or synthesis itself cannot produce a meaningful response.

**Step 5: Verify GREEN**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/host/orchestration tests/backend/test_host_orchestration_engine.py
git commit -m "feat: recover and replan host tasks"
```

---

### Task 5: Integrate LangGraph with the shared engine

**Files:**
- Create: `backend/host/langgraph/decisions.py`
- Modify: `backend/host/langgraph/agent.py`
- Modify: `backend/host/langgraph/manager.py`
- Modify: `backend/main.py`
- Create: `tests/backend/test_langgraph_host_decisions.py`
- Modify: `tests/backend/test_host_tools.py`
- Modify: `tests/backend/test_run_service.py`

**Step 1: Inspect current diffs**

Run: `git diff -- backend/host/langgraph/agent.py backend/host/langgraph/manager.py backend/main.py tests/backend/test_run_service.py`

**Step 2: Write failing adapter tests**

With a fake chat model, prove structured plan parsing, one repair attempt for malformed JSON, public-safe terminal errors, capability context with stable IDs and limitations, structured evaluation, normalized synthesis input, and deterministic rejection of model-proposed unsafe write assignments.

**Step 3: Verify RED**

Run: `pytest -q tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_tools.py`

Expected: `LangGraphDecisionPort` is missing.

**Step 4: Implement decision adapter**

Reuse the existing zero-temperature DeepSeek configuration. Parse model JSON through Pydantic and deterministic validation. Ask for concise Chinese final synthesis. Retain `list_remote_agents` and `send_task` as low-level compatibility tools, but remove the policy that always selects one best Agent.

**Step 5: Switch Auto mode**

Construct the shared engine in `LangGraphHostManager` with the registry and A2A Gateway delegation adapter. Preserve stable IDs, current Run context, approvals, final `done`, and graph/session behavior. Do not alter Direct mode.

**Step 6: Verify**

Run: `pytest -q tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_tools.py tests/backend/test_execution_strategies.py tests/backend/test_run_service.py tests/backend/test_runs_api.py`

Expected: all pass.

**Step 7: Commit**

```bash
git add backend/host/langgraph backend/main.py tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_tools.py tests/backend/test_run_service.py
git commit -m "feat: orchestrate auto runs with LangGraph"
```

---

### Task 6: Normalize and persist orchestration lifecycle events

**Files:**
- Modify: `backend/orchestration/events.py`
- Modify: `backend/orchestration/strategies.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/persistence/models.py`
- Modify: `backend/persistence/repository.py`
- Modify: `tests/backend/test_execution_strategies.py`
- Modify: `tests/backend/test_run_events.py`
- Modify: `tests/backend/test_run_service.py`
- Modify: `tests/backend/test_persistence.py`

**Step 1: Inspect current diffs**

Run: `git diff -- backend/orchestration backend/persistence tests/backend/test_execution_strategies.py tests/backend/test_run_service.py tests/backend/test_persistence.py`

**Step 2: Write failing event tests**

Add typed events: `host.plan_created`, `host.plan_revised`, `host.synthesis_started`, `task.context_prepared`, `task.retry_scheduled`, `task.evaluated`, and `task.blocked`. Prove logical task IDs remain stable across retries; replacement updates Agent metadata; approvals attach to the correct child; concurrent completion still yields strictly increasing sequences; and old events remain readable.

**Step 3: Verify RED**

Run: `pytest -q tests/backend/test_execution_strategies.py tests/backend/test_run_events.py tests/backend/test_run_service.py tests/backend/test_persistence.py`

Expected: unknown event types and transition assertions fail.

**Step 4: Implement additive normalization**

Map engine events into `RunEvent`. Persist only plan summaries, dependency IDs, safe selection/evaluation reasons, and attempt counts—not hidden prompts or sensitive tool output. Update task transitions for retry, replacement, blocked, approval, and truthful root completion. Keep schema version 1 because changes are additive.

**Step 5: Verify**

Run: `pytest -q tests/backend/test_execution_strategies.py tests/backend/test_run_events.py tests/backend/test_run_service.py tests/backend/test_persistence.py tests/backend/test_json_migration.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/orchestration backend/persistence tests/backend/test_execution_strategies.py tests/backend/test_run_events.py tests/backend/test_run_service.py tests/backend/test_persistence.py
git commit -m "feat: persist host orchestration lifecycle"
```

---

### Task 7: Render the multi-Agent plan and recovery trace

**Files:**
- Modify: `frontend/src/state/runEvents.js`
- Modify: `frontend/src/state/runEvents.test.js`
- Modify: `frontend/src/components/OrchestrationTrace.jsx`
- Create: `frontend/src/components/OrchestrationTrace.test.jsx`
- Modify: `frontend/src/styles/workspace.css`
- Modify: `frontend/package.json` and `frontend/package-lock.json` only if component-test support is missing

**Step 1: Inspect and baseline**

Run: `git diff -- frontend/src/state/runEvents.js frontend/src/components/OrchestrationTrace.jsx frontend/src/styles/workspace.css frontend/package.json`

Then run: `npm --prefix frontend test -- --run src/state/runEvents.test.js`

Expected: existing tests pass before editing.

**Step 2: Write failing reducer tests**

Feed plan, parallel, dependency, retry, replacement, evaluation, approval, blocked, and synthesis events. Assert `state.plan.taskIds`, each task's `dependsOn`, attempt count, replacement ID, evaluation, and terminal status. Include an old history without plan events.

**Step 3: Verify RED**

Run: `npm --prefix frontend test -- --run src/state/runEvents.test.js`

Expected: new fields are absent.

**Step 4: Implement reducer support**

Add `plan: null` to empty state and normalize new events additively. Preserve legacy envelopes and `adaptRunStateForLegacy`.

**Step 5: Test and implement the component**

Write component tests for compact single-Agent mode, parallel branches, a shared dependent task, retry/replacement labels, approval, blocked state, and partial completion. Render a small ordered dependency list using existing badges/icons; do not add a graph library or expose hidden prompts.

**Step 6: Verify frontend**

Run:
```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all tests pass and build exits zero.

**Step 7: Commit**

```bash
git add frontend/src/state/runEvents.js frontend/src/state/runEvents.test.js frontend/src/components/OrchestrationTrace.jsx frontend/src/components/OrchestrationTrace.test.jsx frontend/src/styles/workspace.css frontend/package.json frontend/package-lock.json
git commit -m "feat: visualize multi-agent host plans"
```

---

### Task 8: Align ADK with the same orchestration contract

**Files:**
- Create: `backend/host/adk/decisions.py`
- Modify: `backend/host/adk/agent.py`
- Modify: `backend/host/adk/manager.py`
- Create: `tests/backend/test_adk_host_decisions.py`
- Modify: `tests/backend/test_host_tools.py`
- Modify: `tests/backend/test_execution_strategies.py`

**Step 1: Inspect current diffs**

Run: `git diff -- backend/host/adk/agent.py backend/host/adk/manager.py`

**Step 2: Write failing parity tests**

Prove ADK registers/routes duplicate names by stable ID; produces the same plan/evaluation/synthesis contracts as LangGraph; emits equivalent engine events for the same fake decisions/results; and registration refresh does not destroy active Run state.

**Step 3: Verify RED**

Run: `pytest -q tests/backend/test_adk_host_decisions.py tests/backend/test_host_tools.py tests/backend/test_execution_strategies.py`

Expected: ADK still indexes by display name and lacks a decision port.

**Step 4: Implement**

Change registration to `register_agent_card(agent_id, card)` and store connections by stable ID. Implement structured decisions through the existing ADK model API, validated by shared Pydantic contracts. Route the Manager through the same engine, registry, Gateway, limits, retry, and event semantics.

**Step 5: Verify parity**

Run: `pytest -q tests/backend/test_adk_host_decisions.py tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_tools.py tests/backend/test_execution_strategies.py tests/backend/test_run_service.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/host/adk tests/backend/test_adk_host_decisions.py tests/backend/test_host_tools.py tests/backend/test_execution_strategies.py
git commit -m "feat: align ADK host orchestration"
```

---

### Task 9: Add bounded configuration, acceptance tests, and docs

**Files:**
- Modify: `backend/settings.py`
- Modify: `backend/main.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `guide.md`
- Create: `tests/backend/test_host_orchestration_acceptance.py`
- Modify: `tests/backend/test_security.py`
- Modify: `tests/smoke/test_compose_config.py`

**Step 1: Write failing tests**

Require defaults of six tasks, three concurrent delegations, and two attempts. Validate ranges: tasks 1–10, concurrency 1–5, attempts 1–2. Add fake-port acceptance scenarios for one Agent, parallel Ops/Security, serial diagnosis/remediation with approval, retry/replacement, partial result, cancellation, and rejected read-only mutation assignment.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_orchestration_acceptance.py tests/backend/test_security.py tests/smoke/test_compose_config.py`

Expected: bounded settings are missing.

**Step 3: Implement configuration**

Add `HOST_MAX_TASKS`, `HOST_MAX_CONCURRENCY`, and `HOST_MAX_ATTEMPTS` parsing with explicit safe validation. Inject values into the engine; do not read environment variables inside orchestration modules. Add compose defaults.

**Step 4: Update documentation**

Explain Direct versus Auto, the five lifecycle stages, parallel/serial examples, capability metadata, retries and partial results, approval guarantees, configuration limits, and the trace. Do not claim recursive Agent-to-Agent calls.

**Step 5: Verify**

Run: `pytest -q tests/backend/test_host_orchestration_acceptance.py tests/backend/test_security.py tests/smoke/test_compose_config.py`

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/settings.py backend/main.py docker-compose.yml README.md guide.md tests/backend/test_host_orchestration_acceptance.py tests/backend/test_security.py tests/smoke/test_compose_config.py
git commit -m "docs: configure and verify host orchestration"
```

---

### Task 10: Full verification and final diff review

**Step 1: Run all Python tests**

Run: `pytest -q`

Expected: zero failures.

**Step 2: Run frontend tests and build**

Run:
```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: zero failures and Vite exits zero.

**Step 3: Validate Compose**

Run: `docker compose config --quiet`

Expected: exit zero.

**Step 4: Review scope and safety**

Run:
```bash
git status --short
git diff --check
git log --oneline -15
```

Manually verify: Direct mode remains single-Agent; Auto may use one or many Agents; context is bounded and source-labeled; task count, concurrency, and attempts are bounded; independent success survives branch failure; no mutation bypasses approval; both adapters use stable IDs and shared contracts; old registrations and events remain compatible.

**Step 5: Report evidence**

Record exact commands, exit codes, test counts, and environment-dependent checks that could not run. Do not claim completion while any required check fails. If a fix is required, rerun its focused test and all verification commands before committing `fix: address host orchestration verification`.
