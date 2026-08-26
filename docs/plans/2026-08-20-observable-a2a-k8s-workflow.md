# Observable A2A Kubernetes Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Host-led `Security -> K8s Resource Orchestrator -> Ops` A2A workflow that advances automatically, resumes after write approval, preserves every Agent output in the UI, and ends with a separate Host synthesis.

**Architecture:** Keep `/api/runs/stream` as the authoritative execution path. Extend the existing Host DAG with skill-aware validation, persisted plan/task checkpoints, structured delegated results, and a resumable scheduler. Normalize every child Agent stream into task-scoped persisted events, then render one stable result card per child task plus a separate Host summary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy/SQLite, A2A SDK, LangGraph/LangChain model adapter, React, Ant Design, Vitest/Node tests, pytest.

---

### Task 1: Rename the Kubernetes resource Agent without breaking stable identities

**Files:**
- Modify: `agents/k8s-orchestrator/agent.yaml`
- Modify: `agents/k8s-orchestrator/prompt.md`
- Modify: `agents/k8s-orchestrator/.env.example`
- Modify: `README.md`
- Modify: `DESIGN.md`
- Modify: `guide.md`
- Modify: `tests/agents/test_agent_cards.py`
- Modify: `tests/agents/test_agent_configs.py`

**Step 1: Write the failing tests**

Assert that the stable ID remains `k8s-orchestrator`, the public name is `K8s Resource Orchestrator Agent`, resource lifecycle skills remain present, and Helm mutation tools are not owned by this Agent.

```python
def test_resource_orchestrator_keeps_stable_id_and_public_name(config):
    assert config.agent_id == "k8s-orchestrator"
    assert config.name == "K8s Resource Orchestrator Agent"

def test_resource_orchestrator_does_not_own_helm_mutations(config):
    assert "helm_install_chart" not in config.tool_policy.approval_required
```

**Step 2: Run the tests to verify they fail**

Run: `pytest -q tests/agents/test_agent_cards.py tests/agents/test_agent_configs.py`

Expected: FAIL because the old public name and Helm overlap are still present.

**Step 3: Implement the minimal rename**

Change only user-facing names and current responsibility descriptions. Keep the directory, Compose service, port, environment names, and `agent_id` unchanged. Remove `helm_install_chart` from the resource Agent so Helm lifecycle remains with `k8s-helm`.

**Step 4: Run tests**

Run: `pytest -q tests/agents/test_agent_cards.py tests/agents/test_agent_configs.py tests/runtime/test_agent_tool_coverage.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add agents/k8s-orchestrator README.md DESIGN.md guide.md tests/agents
git commit -m "refactor: clarify resource orchestrator responsibility"
```

### Task 2: Add a structured delegated-result contract

**Files:**
- Modify: `backend/host/orchestration/models.py`
- Modify: `backend/host/langgraph/decisions.py`
- Modify: `backend/host/langgraph/manager.py`
- Modify: `backend/a2a_gateway.py`
- Test: `tests/backend/test_host_orchestration_engine.py`
- Test: `tests/backend/test_a2a_gateway.py`

**Step 1: Write failing model and gateway tests**

Cover text-only backward compatibility and structured results containing findings, resources, evidence, recommendations, continuation, and limitations.

```python
def test_delegation_result_accepts_structured_specialist_output():
    result = DelegationResult(
        state="completed",
        text="安全检查通过",
        output={
            "status": "completed",
            "summary": "安全检查通过",
            "continuation": {"allowed": True, "reason": "no blockers"},
        },
    )
    assert result.output.continuation.allowed is True
```

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py tests/backend/test_a2a_gateway.py`

Expected: FAIL because `DelegationResult` has no structured `output`.

**Step 3: Implement the contract**

Add Pydantic models with defaults so legacy text-only Agents remain valid:

```python
class Continuation(BaseModel):
    allowed: bool | None = None
    reason: str = ""

class SpecialistOutput(BaseModel):
    status: str = "completed"
    summary: str = ""
    findings: list[dict] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    continuation: Continuation = Field(default_factory=Continuation)
    limitations: list[str] = Field(default_factory=list)
```

Preserve A2A artifacts in the gateway and extract an artifact named `specialist_result` when present. Keep `text` as the fallback display value.

**Step 4: Make Host evaluation deterministic where possible**

If `continuation.allowed` is explicitly false, return `blocked` without asking the Host model. If state failed, return failed. Use model evaluation only for compatible text-only results or quality evaluation.

**Step 5: Run tests and commit**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py tests/backend/test_a2a_gateway.py tests/backend/test_a2a_client.py`

Expected: PASS.

```bash
git add backend/host backend/a2a_gateway.py tests/backend
git commit -m "feat: add structured specialist result contract"
```

### Task 3: Enforce skill-aware Host plans and guarded Kubernetes mutations

**Files:**
- Modify: `backend/host/orchestration/models.py`
- Modify: `backend/host/orchestration/validation.py`
- Modify: `backend/host/langgraph/decisions.py`
- Modify: `backend/registry/service.py`
- Test: `tests/backend/test_host_plan_validation.py`
- Test: `tests/backend/test_registry.py`
- Test: `tests/backend/test_langgraph_host_decisions.py`

**Step 1: Write failing validation tests**

Add `required_skill` and `required_tags` to planned tasks. Prove that unknown skills, incompatible risk, wrong Agent ownership, and missing guarded deployment stages are rejected.

```python
def test_write_task_requires_matching_agent_skill():
    plan = HostPlan(tasks=[planned(
        "change", "k8s-ops", risk="write",
        required_skill="resource.manage",
    )])
    with pytest.raises(PlanValidationError, match="required skill"):
        validate_plan(plan, profiles)
```

Add a deployment invariant test requiring a security predecessor and post-change verification successor for a guarded Kubernetes mutation.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_plan_validation.py tests/backend/test_registry.py tests/backend/test_langgraph_host_decisions.py`

Expected: FAIL because plans do not carry required capabilities.

**Step 3: Implement minimal skill validation**

Make the Host model emit a required skill or tags for each delegated task. Validate these against Agent Cards. Pass the same skill/tags to `rank_candidates()` so fallback never chooses an unrelated write-capable Agent.

**Step 4: Add guarded mutation validation**

Represent workflow roles explicitly (`precheck`, `mutation`, `verification`) on `PlannedTask`. For Kubernetes deployment mutations, require dependencies equivalent to:

```text
precheck -> mutation -> verification
```

Do not apply this invariant to read-only requests or standalone non-deployment mutations.

**Step 5: Run tests and commit**

Run: `pytest -q tests/backend/test_host_plan_validation.py tests/backend/test_registry.py tests/backend/test_langgraph_host_decisions.py tests/backend/test_host_orchestration_engine.py`

Expected: PASS.

```bash
git add backend/host backend/registry tests/backend
git commit -m "feat: validate host plans against agent skills"
```

### Task 4: Persist Host plan checkpoints and task terminal results

**Files:**
- Modify: `backend/persistence/repository.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/host/orchestration/engine.py`
- Test: `tests/backend/test_persistence.py`
- Test: `tests/backend/test_run_service.py`

**Step 1: Write failing persistence tests**

Test repository methods that merge Run data and task data without losing existing fields.

```python
repository.update_run_data("run-1", {"host_plan": plan.model_dump()})
repository.update_task_data("task-1", {
    "delegation_result": result.model_dump(),
    "logical_task_id": "security-review",
})
assert repository.get_run("run-1")["host_plan"] == plan.model_dump()
```

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_persistence.py tests/backend/test_run_service.py`

Expected: FAIL because merge helpers/checkpoints do not exist.

**Step 3: Implement repository merge operations**

Add transactional `update_run_data()` and `update_task_data()` operations. Persist the validated Host plan before delegation begins. Persist each terminal `DelegationResult`, evaluation, logical task ID, and dependency list on its child task.

**Step 4: Expose resumable state**

Add a service method that reconstructs:

```python
HostCheckpoint(
    plan=HostPlan.model_validate(run["host_plan"]),
    results=terminal_results_by_logical_id,
    successful=completed_logical_ids,
    paused_task_id=run.get("paused_task_id"),
)
```

**Step 5: Run tests and commit**

Run: `pytest -q tests/backend/test_persistence.py tests/backend/test_run_service.py`

Expected: PASS.

```bash
git add backend/persistence backend/orchestration/service.py backend/host/orchestration/engine.py tests/backend
git commit -m "feat: persist host orchestration checkpoints"
```

### Task 5: Make every Agent output task-scoped and replayable

**Files:**
- Modify: `backend/host/langgraph/manager.py`
- Modify: `backend/host/orchestration/engine.py`
- Modify: `backend/orchestration/strategies.py`
- Modify: `backend/orchestration/service.py`
- Test: `tests/backend/test_execution_strategies.py`
- Test: `tests/backend/test_run_service.py`
- Test: `tests/backend/test_event_feed.py`

**Step 1: Write failing event-order tests**

Feed interleaved Security and Infrastructure streams and prove every `message.delta`, `message.completed`, `tool.called`, and `tool.completed` event receives the correct Host child `task_id` and `agent_id`.

Assert ordering:

```text
task.started
message.delta*
message.completed
task.completed
```

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_execution_strategies.py tests/backend/test_run_service.py tests/backend/test_event_feed.py`

Expected: FAIL where child Agent text is accumulated only for Host synthesis or lacks child identity.

**Step 3: Emit task-scoped Agent text**

Make `_delegate_task()` forward remote text chunks through `on_event`. Normalize them into child `MESSAGE_DELTA` events. Emit one child `MESSAGE_COMPLETED` before the child terminal event. Keep Host synthesis messages on the root Host task.

**Step 4: Persist child messages**

Update `RunService` to save a separate assistant message for each completed child output with metadata:

```json
{
  "source": "delegated_agent",
  "run_id": "...",
  "task_id": "...",
  "agent_id": "k8s-security"
}
```

Do not let these messages set the root `assistant_saved` flag.

**Step 5: Test replay and commit**

Run: `pytest -q tests/backend/test_execution_strategies.py tests/backend/test_run_service.py tests/backend/test_runs_api.py tests/backend/test_event_feed.py`

Expected: PASS.

```bash
git add backend/host backend/orchestration tests/backend
git commit -m "feat: preserve task scoped agent output"
```

### Task 6: Resume the same Host DAG after approval

**Files:**
- Modify: `backend/host/orchestration/engine.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/approvals/service.py`
- Modify: `backend/api/runs.py`
- Test: `tests/backend/test_host_orchestration_engine.py`
- Test: `tests/backend/test_approval_service.py`
- Test: `tests/backend/test_run_service.py`
- Test: `tests/backend/test_runs_api.py`

**Step 1: Write the failing acceptance test**

Create a three-task plan:

```text
security-review -> resource-change -> ops-verify
```

The security task completes, resource change returns approval-required, and the Run pauses. After approval continuation returns completed, assert that:

- the same resource child task becomes completed;
- the resource task is not delegated a second time;
- `ops-verify` starts automatically;
- Host synthesis includes all three terminal results;
- Security output remains persisted.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py tests/backend/test_approval_service.py tests/backend/test_run_service.py tests/backend/test_runs_api.py`

Expected: FAIL because approval completion currently summarizes without resuming the scheduler.

**Step 3: Split scheduling from initial planning**

Refactor `HostOrchestrationEngine` into:

```python
async def create_and_stream(request, run_id): ...
async def resume_and_stream(request, run_id, checkpoint): ...
async def stream_plan(request, run_id, plan, results, successful): ...
```

`stream_plan()` skips persisted terminal tasks and schedules only newly ready tasks.

**Step 4: Connect approval continuation**

After `ApprovalService.decide()` continues the remote A2A task, attach its result to the paused child task, persist `approval.decided`, mark the Run running, and call `RunService.resume_after_approval(run_id)`. Persist all resumed events before returning the API response.

Use one per-Run lock so duplicate approval requests or reconnects cannot resume the same graph twice.

**Step 5: Handle rejection**

Persist the mutation task as blocked, mark dependents blocked, then synthesize partial results. Do not run Ops verification.

**Step 6: Run tests and commit**

Run: `pytest -q tests/backend/test_host_orchestration_engine.py tests/backend/test_approval_service.py tests/backend/test_run_service.py tests/backend/test_runs_api.py`

Expected: PASS.

```bash
git add backend/host backend/orchestration backend/approvals backend/api/runs.py tests/backend
git commit -m "feat: resume host workflow after approval"
```

### Task 7: Render persistent per-Agent result cards and a separate Host summary

**Files:**
- Modify: `frontend/src/state/runEvents.js`
- Modify: `frontend/src/state/runEvents.test.js`
- Create: `frontend/src/components/workspace/AgentResultCard.jsx`
- Create: `frontend/src/components/workspace/AgentResultCard.test.jsx`
- Modify: `frontend/src/components/workspace/RunTimeline.jsx`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`
- Modify: `frontend/src/components/workspace/MessageTimeline.jsx`
- Modify: `frontend/src/pages/WorkspacePage.jsx`
- Modify: `frontend/src/styles/workspace.css`

**Step 1: Write failing reducer tests**

Prove that task-scoped message deltas accumulate on the matching task, completed outputs survive later events, approvals attach to the mutation task, and root Host messages remain separate.

```javascript
assert.equal(state.tasksById.security.output, '安全检查通过')
assert.equal(state.tasksById.change.status, 'working')
assert.equal(state.hostSummary, '部署完成且验证正常')
```

**Step 2: Verify RED**

Run: `npm test -- --run src/state/runEvents.test.js`

Expected: FAIL because messages are stored globally and cards lack final output.

**Step 3: Update normalized state**

Store task text, tools, approval IDs, final result, timestamps, and errors under `tasksById[taskId]`. Store root Host synthesis separately as `hostSummary`. Preserve event replay and legacy normalization.

**Step 4: Write failing component tests**

Render three planned tasks and assert that completed Security output remains visible while Resource Orchestrator is active, Ops is pending, and Host summary appears only in a separate section.

**Step 5: Implement cards**

Render one `AgentResultCard` per planned task in plan order. Each card shows identity, objective, state, streaming/final text, MCP activity, approval, and errors. Do not hide completed cards when the next task starts.

**Step 6: Run frontend tests and commit**

Run: `npm test -- --run`

Expected: PASS.

```bash
git add frontend/src
git commit -m "feat: display every agent workflow result"
```

### Task 8: Unify or deprecate the legacy Host endpoints

**Files:**
- Modify: `backend/main.py`
- Modify: `frontend/src/api/api.js`
- Test: `tests/backend/test_runs_api.py`
- Test: `tests/backend/test_backend_import_mode.py`

**Step 1: Write failing compatibility tests**

Prove that `/api/host/send` and `/api/host/send-stream` no longer run keyword-based single-Agent routing. They should return a deprecation response pointing to `/api/runs/stream`, or translate into a unified auto `RunCommand`.

**Step 2: Verify RED**

Run: `pytest -q tests/backend/test_runs_api.py tests/backend/test_backend_import_mode.py`

Expected: FAIL because the legacy router still selects one Agent by keywords.

**Step 3: Remove the duplicate execution behavior**

Prefer a compatibility adapter to the unified Run service if clients still use these endpoints; otherwise return HTTP 410 with a migration message. Remove unused frontend API helpers after confirming no callers remain.

**Step 4: Run tests and commit**

Run: `pytest -q tests/backend/test_runs_api.py tests/backend/test_backend_import_mode.py`

Expected: PASS.

```bash
git add backend/main.py frontend/src/api/api.js tests/backend
git commit -m "refactor: unify host execution api"
```

### Task 9: Add the complete observable workflow acceptance test

**Files:**
- Create: `tests/e2e/test_observable_a2a_workflow.py`
- Create: `tests/fixtures/a2a_agents.py`
- Modify: `tests/backend/test_agent_decoupling.py`

**Step 1: Build deterministic stub A2A Agents**

Provide Security, Resource Orchestrator, and Ops Agent Cards and streams. The resource Agent must pause once for approval and complete only when continued with the same context/task binding.

**Step 2: Write the end-to-end test**

Assert the complete sequence:

```text
Host plan
Security output
Resource approval
Approval continuation
Resource output
Ops output
Host summary
Run completed
```

Also assert each child has a distinct Host task ID and that replay returns the same output ordering.

**Step 3: Run and fix only integration defects**

Run: `pytest -q tests/e2e/test_observable_a2a_workflow.py`

Expected: PASS.

**Step 4: Commit**

```bash
git add tests/e2e tests/fixtures tests/backend/test_agent_decoupling.py
git commit -m "test: cover observable a2a kubernetes workflow"
```

### Task 10: Final verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `DESIGN.md`
- Modify: `guide.md`
- Modify: `docs/CODE_WALKTHROUGH_ZH.md`

**Step 1: Document the authoritative flow**

Document Host A2A orchestration, specialist MCP execution, automatic read-only advancement, approval pause/resume, per-Agent result cards, and the separate Host synthesis.

**Step 2: Run complete backend verification**

Run: `pytest -q`

Expected: all tests pass with only documented dependency deprecation warnings.

**Step 3: Run complete frontend verification**

Run: `cd frontend && npm test -- --run && npm run build`

Expected: all tests pass and the Vite build succeeds.

**Step 4: Run static/configuration checks**

Run: `python -m compileall -q agents backend`

Run: `docker compose config >/dev/null`

Run: `git diff --check`

Expected: all commands exit zero.

**Step 5: Optional live smoke test**

With the configured Streamable HTTP MCP server reachable, run the nginx acceptance scenario against a non-production namespace. Do not execute the mutation without explicit approval in the UI.

**Step 6: Commit documentation**

```bash
git add README.md DESIGN.md guide.md docs/CODE_WALKTHROUGH_ZH.md
git commit -m "docs: explain observable a2a workflow"
```
