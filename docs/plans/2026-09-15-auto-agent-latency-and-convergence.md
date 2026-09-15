# Auto Agent Latency and Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent independent Auto tasks from accumulating prior Agent tool history and make useful partial diagnostics converge into a Host answer instead of repeating full audits.

**Architecture:** Pass each logical Host task ID through the gateway and derive a task-scoped A2A context ID, while preserving the existing binding only for approval continuation. Treat non-empty partial specialist output as usable evidence and give the ReAct engine a deterministic synthesis fallback when it reaches its diagnostic round limit.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, A2A SDK, PostgreSQL checkpointing, pytest/anyio.

---

### Task 1: Isolate independent delegated task checkpoints

**Files:**
- Modify: `backend/host/orchestration/engine.py`
- Modify: `backend/a2a_gateway.py`
- Test: `tests/backend/test_a2a_gateway.py`
- Test: `tests/backend/test_host_orchestration_engine.py`

**Step 1: Write failing tests**

Add tests proving that two ordinary logical tasks sent to the same Agent receive different context IDs, while an approval continuation reuses the binding created for its logical task. Add an engine test proving the logical task ID reaches a four-argument delegate.

**Step 2: Verify RED**

Run:

```bash
pytest -q tests/backend/test_a2a_gateway.py tests/backend/test_host_orchestration_engine.py
```

Expected: the new context-isolation and delegate-signature tests fail because the gateway only scopes contexts by conversation and Agent, and the engine does not pass the task ID.

**Step 3: Implement the smallest production change**

Extend the delegate boundary with `logical_task_id`. Generate ordinary context IDs from conversation, Agent, and logical task. Look up and reuse a binding only for an approval continuation. Keep Direct mode compatible by using its root task ID.

**Step 4: Verify GREEN**

Run the two test files again and expect all tests to pass.

**Step 5: Commit**

```bash
git add backend/a2a_gateway.py backend/host/orchestration/engine.py tests/backend/test_a2a_gateway.py tests/backend/test_host_orchestration_engine.py
git commit -m "fix: isolate delegated agent checkpoints"
```

### Task 2: Converge useful partial diagnostic results

**Files:**
- Modify: `backend/host/langgraph/decisions.py`
- Modify: `backend/host/orchestration/engine.py`
- Test: `tests/backend/test_langgraph_host_decisions.py`
- Test: `tests/backend/test_host_orchestration_engine.py`

**Step 1: Write failing tests**

Add a decision-port test proving a partial result with a non-empty summary is usable without another model evaluation. Add an engine test proving a diagnostic run synthesizes accumulated evidence at the configured round boundary instead of raising `Host ReAct round budget exhausted`.

**Step 2: Verify RED**

Run:

```bash
pytest -q tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_orchestration_engine.py
```

Expected: the useful partial result is `insufficient` and the engine raises at the round boundary.

**Step 3: Implement the smallest production change**

Classify a non-empty partial summary as sufficient evidence for read-only diagnostics while keeping empty partial output insufficient. Add a ReAct synthesis method that receives compact observations, and invoke it when the configured round boundary is reached.

**Step 4: Verify GREEN**

Run the two test files again and expect all tests to pass.

**Step 5: Commit**

```bash
git add backend/host/langgraph/decisions.py backend/host/orchestration/engine.py tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_orchestration_engine.py
git commit -m "fix: converge partial auto diagnostics"
```

### Task 3: Bound forced-summary evidence to the current invocation

**Files:**
- Modify: `agents/shared-runtime/a2a_runtime/agent.py`
- Modify: `agents/shared-runtime/a2a_runtime/streaming.py`
- Test: `tests/runtime/test_mcp_client.py`
- Test: `tests/runtime/test_streaming.py`

**Step 1: Write failing tests**

Add tests proving forced-summary evidence contains only tool results observed during the current `stream()` invocation, de-duplicates call IDs, and obeys a small total bound. Add a test for the public `summarizing` progress event.

**Step 2: Verify RED**

Run:

```bash
pytest -q tests/runtime/test_mcp_client.py tests/runtime/test_streaming.py
```

Expected: the current implementation reads all historical ToolMessages from the checkpoint and has no summarizing event.

**Step 3: Implement the smallest production change**

Collect current-run tool results while streaming, pass them directly to forced and deterministic summary helpers, cap each result and the total evidence size, and emit a summarizing status before final generation.

**Step 4: Verify GREEN**

Run the two runtime test files and expect all tests to pass.

**Step 5: Commit**

```bash
git add agents/shared-runtime/a2a_runtime/agent.py agents/shared-runtime/a2a_runtime/streaming.py tests/runtime/test_mcp_client.py tests/runtime/test_streaming.py
git commit -m "perf: bound agent summary evidence"
```

### Task 4: Regression and page-level verification

**Files:**
- No production files expected
- Update documentation only if observed behavior differs from the design

**Step 1: Run focused backend and runtime tests**

```bash
pytest -q tests/backend/test_a2a_gateway.py tests/backend/test_host_orchestration_engine.py tests/backend/test_langgraph_host_decisions.py tests/backend/test_execution_strategies.py tests/runtime/test_mcp_client.py tests/runtime/test_streaming.py
```

Expected: PASS.

**Step 2: Run the full non-Postgres suite**

```bash
pytest -q tests/backend tests/runtime
```

Expected: PASS.

**Step 3: Restart affected local services**

Restart backend, `k8s-ops`, and `k8s-security` using the repository's existing local process workflow without exposing API keys.

**Step 4: Repeat the Auto page test**

From a fresh Auto conversation, submit `检查集群有什么问题`. Capture browser trace and Run events. Verify that independent tasks have different context IDs, the Host produces a final answer without six near-identical rounds, and record the first-round and total wall-clock durations.

**Step 5: Commit any verification documentation**

Only if documentation changes were required, commit them separately.
