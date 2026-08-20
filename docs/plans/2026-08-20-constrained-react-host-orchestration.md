# Constrained ReAct Host Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace one-shot Auto Host DAG planning with bounded ReAct rounds that can delegate parallel Agent tasks, observe their actual results, and dynamically choose the next action.

**Architecture:** Introduce a framework-neutral `HostDecision` and persisted `HostRunState`; let the decision port choose one action per round and keep the existing task executor for parallel A2A delegation. Normalize new round events through the existing Run service and frontend reducer while retaining legacy one-shot event replay and Direct mode.

**Tech Stack:** Python 3.12, asyncio, Pydantic v2, LangChain structured output, FastAPI, SQLite repository, React, Vite, Node test runner, pytest.

---

## Working-tree constraint

The repository contains unrelated uncommitted user work. Do not reset, stash, or
bulk-format the worktree. Before every commit, inspect `git diff --name-only` and
stage only files named by the current task.

### Task 1: Define the per-round decision and checkpoint contracts

**Files:**
- Modify: `backend/host/orchestration/models.py`
- Modify: `backend/host/orchestration/__init__.py`
- Create: `tests/backend/test_host_react_models.py`

**Step 1: Write failing model tests**

Add tests proving:

```python
def test_delegate_decision_requires_tasks():
    with pytest.raises(ValidationError):
        HostDecision(action="delegate", reason="inspect", tasks=[])


def test_terminal_decision_rejects_tasks():
    with pytest.raises(ValidationError):
        HostDecision(
            action="complete",
            reason="done",
            response="healthy",
            tasks=[planned_task("unexpected")],
        )


def test_react_state_round_trips_structured_observations():
    state = HostRunState(
        goal="deploy nginx",
        round=1,
        observations={"security-1": observed_security_block()},
    )
    assert HostRunState.model_validate(state.model_dump()) == state
```

Also test action rules:

- `delegate`: one to three tasks, empty response.
- `clarify`, `request_approval`, `complete`, `stop`: no tasks and non-empty response.
- Task IDs are unique inside one decision.
- `HostRunState` tracks decisions, task results, successful IDs, fingerprints,
  pending approval, total task count, and round number.

**Step 2: Run tests and verify RED**

Run:

```bash
pytest -q tests/backend/test_host_react_models.py
```

Expected: collection/import failure because `HostDecision` and `HostRunState` do
not exist.

**Step 3: Implement minimal Pydantic contracts**

Add:

```python
class HostDecision(BaseModel):
    action: Literal[
        "delegate", "clarify", "request_approval", "complete", "stop"
    ]
    reason: str = Field(min_length=1)
    response: str = ""
    tasks: list[PlannedTask] = Field(default_factory=list, max_length=3)


class ObservedTask(BaseModel):
    task: PlannedTask
    result: DelegationResult
    evaluation: Evaluation
    actual_agent_id: str


class HostRunState(BaseModel):
    goal: str
    round: int = Field(default=0, ge=0)
    decisions: list[HostDecision] = Field(default_factory=list)
    observations: dict[str, ObservedTask] = Field(default_factory=dict)
    successful: set[str] = Field(default_factory=set)
    task_fingerprints: set[str] = Field(default_factory=set)
    pending_approval_task_id: str | None = None
    total_tasks: int = Field(default=0, ge=0)
```

Keep `HostPlan` temporarily for persisted legacy Runs and compatibility tests.
Extend `DecisionPort` with `decide_next(request, agents, state)`; do not remove
legacy methods until migration tests pass.

**Step 4: Run tests and verify GREEN**

Run:

```bash
pytest -q tests/backend/test_host_react_models.py tests/backend/test_host_plan_validation.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/host/orchestration/models.py backend/host/orchestration/__init__.py tests/backend/test_host_react_models.py
git commit -m "feat: define host react decision state"
```

### Task 2: Validate dynamic decisions and workflow invariants

**Files:**
- Modify: `backend/host/orchestration/validation.py`
- Modify: `tests/backend/test_host_plan_validation.py`

**Step 1: Write failing validation tests**

Add tests for `validate_decision(decision, profiles, state)`:

```python
def test_rejects_duplicate_semantic_task_from_later_round(): ...
def test_rejects_mutation_without_successful_security_observation(): ...
def test_accepts_parallel_read_checks_in_same_round(): ...
def test_accepts_mutation_after_security_allows_continuation(): ...
def test_rejects_complete_after_mutation_without_verification(): ...
def test_accepts_terminal_stop_after_blocking_precheck(): ...
```

Use a deterministic fingerprint derived from normalized `agent_id`, objective,
risk, workflow role, required skill, and input. Verify a repeated write is rejected
even when it has a new task ID.

**Step 2: Run tests and verify RED**

```bash
pytest -q tests/backend/test_host_plan_validation.py -k react
```

Expected: FAIL because `validate_decision` is absent.

**Step 3: Implement minimal decision validation**

Reuse current skill/tag/read-only checks by extracting a single-task validator.
For mutation guards, inspect only structured observations:

```python
security_passed = any(
    observed.task.workflow_role == "precheck"
    and observed.evaluation.outcome == "sufficient"
    and observed.result.output is not None
    and observed.result.output.continuation.allowed is True
    for observed in state.observations.values()
)
```

Track whether a successful mutation exists without a later sufficient verification;
reject `complete` in that state. Allow `stop` and `clarify` after blockers.

**Step 4: Run validation suites**

```bash
pytest -q tests/backend/test_host_plan_validation.py tests/backend/test_host_react_models.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/host/orchestration/validation.py tests/backend/test_host_plan_validation.py
git commit -m "feat: validate host react decisions"
```

### Task 3: Make LangGraph choose the next round from observations

**Files:**
- Modify: `backend/host/langgraph/decisions.py`
- Modify: `tests/backend/test_langgraph_host_decisions.py`

**Step 1: Write failing decision-port tests**

Add tests proving that:

- `decide_next()` requests `HostDecision`, not a complete future DAG.
- The structured payload contains the original goal, current round, compact prior
  observations, budgets, and available Agent profiles.
- A Security observation with `continuation.allowed=false` is visible to the next
  decision.
- The system instruction allows one to three independent parallel tasks.
- The system instruction forbids hidden chain-of-thought and asks only for a concise
  public reason.
- Invalid structured output raises `RuntimeError("Unable to create a valid Host decision")`.

**Step 2: Run tests and verify RED**

```bash
pytest -q tests/backend/test_langgraph_host_decisions.py -k decide_next
```

Expected: FAIL because only `create_plan()` exists.

**Step 3: Implement `decide_next()`**

Build a compact JSON payload. Limit raw `result.text` included in the decision
prompt; preserve structured `output`, evaluation and task metadata. Invoke structured
output with `HostDecision`, then call `validate_decision`.

Keep `evaluate()` and `synthesize()` unchanged except broaden synthesis input to
accept `HostRunState` or a deterministic projection of its observations.

**Step 4: Run decision tests**

```bash
pytest -q tests/backend/test_langgraph_host_decisions.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/host/langgraph/decisions.py tests/backend/test_langgraph_host_decisions.py
git commit -m "feat: decide host actions from observations"
```

### Task 4: Replace the one-shot DAG loop with bounded ReAct rounds

**Files:**
- Modify: `backend/host/orchestration/engine.py`
- Modify: `tests/backend/test_host_orchestration_engine.py`
- Modify: `tests/backend/test_host_orchestration_acceptance.py`

**Step 1: Write the first failing engine test**

Create a fake decision port that returns:

1. `delegate` with Security and Capacity tasks.
2. `clarify` after it receives a Security observation that the namespace is absent.

Assert:

```python
assert calls == ["security", "capacity"]
assert decision_states[1].observations.keys() == {"security-1", "capacity-1"}
assert not any(event["agent_id"] == "orchestrator" for event in routed_events)
assert not any(event["type"] == "task_blocked" for event in events)
```

**Step 2: Run it and verify RED**

```bash
pytest -q tests/backend/test_host_orchestration_engine.py -k next_round
```

Expected: FAIL because the engine calls `create_plan()` once.

**Step 3: Implement the minimal round loop**

Refactor existing ready-task execution into `_execute_round()`. The outer loop:

```python
while state.round < self._max_rounds:
    state.round += 1
    yield {"type": "round_started", "round": state.round}
    decision = await self._decisions.decide_next(request, agents, state)
    validate_decision(decision, profiles, state)
    yield {"type": "decision_created", ...}
    if decision.action != "delegate":
        yield terminal_or_pause_event(decision)
        return
    executions = await self._execute_round(...)
    append_observations(state, executions)
    yield {"type": "round_completed", ...}
```

Reuse `_run_task`, `_execute_safely`, progress streaming, retry, replacement and
the existing semaphore. Each task prompt receives the original goal plus only the
prior observations needed for the stated objective.

**Step 4: Add and run parallel-round test**

Use `asyncio.Event` to prove two tasks in one decision start before either finishes:

```bash
pytest -q tests/backend/test_host_orchestration_engine.py -k parallel_round
```

Expected: RED, then GREEN after sharing the existing `asyncio.gather()` executor.

**Step 5: Add and run dynamic-later-task test**

Return Security in round 1, Resource Orchestrator in round 2, Ops in round 3, and
`complete` in round 4. Assert later tasks were not present in the first decision
event and calls occur in the expected round order.

```bash
pytest -q tests/backend/test_host_orchestration_engine.py -k dynamic_later_task
```

Expected: PASS after minimal implementation.

**Step 6: Add budget and partial-failure tests**

Verify:

- `max_rounds` terminates repeated delegation.
- `max_total_tasks` rejects task expansion.
- successful parallel observations survive another task's failure.
- duplicate semantic tasks never execute.

Run:

```bash
pytest -q tests/backend/test_host_orchestration_engine.py
```

Expected: PASS.

**Step 7: Update acceptance test**

Change the acceptance sequence to dynamic rounds and assert Security output exists
before the mutation decision is requested and Ops is decided only after mutation
completion.

```bash
pytest -q tests/backend/test_host_orchestration_acceptance.py
```

Expected: PASS.

**Step 8: Commit**

```bash
git add backend/host/orchestration/engine.py tests/backend/test_host_orchestration_engine.py tests/backend/test_host_orchestration_acceptance.py
git commit -m "feat: orchestrate agents in react rounds"
```

### Task 5: Persist ReAct checkpoints and resume after approval

**Files:**
- Modify: `backend/host/langgraph/manager.py`
- Modify: `backend/orchestration/service.py`
- Modify: `backend/persistence/repository.py`
- Modify: `tests/backend/test_run_service.py`
- Modify: `tests/backend/test_approval_service.py`
- Modify: `tests/backend/test_persistence.py`

**Step 1: Write failing checkpoint persistence test**

Stream two completed rounds and assert `repository.get_run(run_id)["host_state"]`
can be validated as `HostRunState` with both observations.

```bash
pytest -q tests/backend/test_run_service.py -k react_checkpoint
```

Expected: FAIL because only `host_plan` is stored.

**Step 2: Implement checkpoint event/data propagation**

Have the Host engine attach a serializable `checkpoint` to `decision_created`,
`round_completed`, and approval pause events. In `AutoExecutionStrategy` and
`RunService`, persist it through `update_run_data` as `host_state` before streaming
the associated event.

Do not remove reading `host_plan`; `_host_checkpoint()` must detect:

```python
if run.get("host_state"):
    return HostRunState.model_validate(run["host_state"])
return migrate_legacy_plan_checkpoint(run)
```

**Step 3: Run persistence test**

```bash
pytest -q tests/backend/test_persistence.py tests/backend/test_run_service.py -k 'checkpoint or host_state'
```

Expected: PASS.

**Step 4: Write failing approval-resume test**

Model four rounds: Security, write approval, approved write observation, Ops, then
complete. Assert the write Agent is not delegated twice and the post-approval call
to `decide_next()` receives the approved write result.

```bash
pytest -q tests/backend/test_approval_service.py -k react_resume
```

Expected: FAIL using legacy plan resume.

**Step 5: Implement same-task approval resume**

Update `resume_message_stream()` and `RunService.resume_after_approval()` to pass
`HostRunState`. Attach the resumed result to the pending task, clear
`pending_approval_task_id`, persist the checkpoint, then enter the next Host round.
On rejection, add a blocked observation and forbid re-proposal via its fingerprint.

**Step 6: Run approval and service suites**

```bash
pytest -q tests/backend/test_approval_service.py tests/backend/test_run_service.py tests/backend/test_persistence.py
```

Expected: PASS.

**Step 7: Commit**

```bash
git add backend/host/langgraph/manager.py backend/orchestration/service.py backend/persistence/repository.py tests/backend/test_run_service.py tests/backend/test_approval_service.py tests/backend/test_persistence.py
git commit -m "feat: persist and resume host react state"
```

### Task 6: Normalize round events without breaking legacy Runs

**Files:**
- Modify: `backend/orchestration/events.py`
- Modify: `backend/orchestration/strategies.py`
- Modify: `tests/backend/test_execution_strategies.py`
- Modify: `tests/backend/test_event_feed.py`

**Step 1: Write failing strategy event test**

Feed upstream `round_started`, `decision_created`, and `round_completed`. Assert the
normalized sequence is:

```text
host.round_started
host.decision_created
task.delegated ...
host.round_completed
```

and each delegated task obtains one stable backend task ID. Add a second decision
and assert its new tasks append rather than replace earlier mappings.

**Step 2: Run and verify RED**

```bash
pytest -q tests/backend/test_execution_strategies.py -k react_round_events
```

Expected: FAIL because the event enum and adapter cases do not exist.

**Step 3: Implement event normalization**

Add enum members and adapter cases. Extract the task registration logic currently
inside `plan_created` so both `plan_created` and `decision_created` reuse it. Preserve
legacy `host.plan_created` behavior exactly.

**Step 4: Test replay/feed descriptions**

```bash
pytest -q tests/backend/test_execution_strategies.py tests/backend/test_event_feed.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/orchestration/events.py backend/orchestration/strategies.py tests/backend/test_execution_strategies.py tests/backend/test_event_feed.py
git commit -m "feat: stream host react round events"
```

### Task 7: Append ReAct rounds and tasks in frontend state

**Files:**
- Modify: `frontend/src/state/runEvents.js`
- Modify: `frontend/src/state/runEvents.test.js`

**Step 1: Write failing reducer tests**

Add a test that reduces two `host.decision_created` events. The first contains
Security and Capacity; the second contains Resource Orchestrator. Assert:

```javascript
assert.deepEqual(state.roundOrder, [1, 2])
assert.deepEqual(state.roundsByNumber[1].taskIds, ['security', 'capacity'])
assert.deepEqual(state.roundsByNumber[2].taskIds, ['orchestrator'])
assert.deepEqual(state.taskOrder, ['security', 'capacity', 'orchestrator'])
```

Replay `rawEvents` and assert identical state. Add a legacy `host.plan_created` test
to prove compatibility.

**Step 2: Run and verify RED**

```bash
cd frontend && node --test src/state/runEvents.test.js
```

Expected: FAIL because round state is not represented.

**Step 3: Implement minimal reducer state**

Add `roundsByNumber` and `roundOrder` to `emptyRunState`. Extract task insertion from
the existing plan branch, reuse it for `host.decision_created`, and merge rather than
replace task order. Handle `host.round_started`/`completed` statuses.

**Step 4: Run reducer tests**

```bash
cd frontend && node --test src/state/runEvents.test.js
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/state/runEvents.js frontend/src/state/runEvents.test.js
git commit -m "feat: retain incremental host decision rounds"
```

### Task 8: Display Host decisions and progressive Agent cards

**Files:**
- Modify: `frontend/src/components/workspace/RunTimeline.jsx`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`
- Modify: `frontend/src/styles/workspace.css`
- Test: relevant existing frontend component/state tests; add a focused component test only if the repository already has a renderer configured.

**Step 1: Write the smallest failing view-model test**

If timeline rendering is pure JSX without a configured component test harness,
extract a pure `buildRoundTimeline(state)` helper and test it. Assert that parallel
tasks share one round, later tasks appear only after their decision event, and Host
reason text is displayed separately from Agent output.

Run the focused test and confirm RED.

**Step 2: Implement progressive round rendering**

Render a compact Host decision row per round with public reason and status. Nest or
visually group that round's Agent cards without changing their existing message,
tool, approval, and result displays. Preserve legacy flat-plan rendering when
`roundOrder` is empty.

**Step 3: Run frontend tests and build**

```bash
cd frontend && npm test
cd frontend && npm run build
```

Expected: all tests PASS and Vite build succeeds.

**Step 4: Commit**

```bash
git add frontend/src/components/workspace/RunTimeline.jsx frontend/src/components/workspace/RunTracePanel.jsx frontend/src/styles/workspace.css frontend/src/state
git commit -m "feat: show progressive host react rounds"
```

### Task 9: Settings, compatibility regression, and documentation

**Files:**
- Modify: `backend/settings.py`
- Modify: `backend/.env.example`
- Modify: `.env.example` only if it still exists in the intended final tree; do not recreate a user-deleted file without confirming repository convention.
- Modify: `docker-compose.yml`
- Modify: `tests/backend/test_llm_config.py` or create focused settings tests
- Modify: `docs/CODE_WALKTHROUGH_ZH.md`
- Modify: `README.md`

**Step 1: Write failing settings tests**

Test defaults and bounds for:

```text
HOST_MAX_ROUNDS=8
HOST_MAX_TASKS=12
HOST_MAX_ROUND_TASKS=3
```

Keep existing `HOST_MAX_CONCURRENCY`, attempts and model timeout settings.

**Step 2: Run and verify RED**

```bash
pytest -q tests/backend/test_llm_config.py
```

Expected: FAIL for missing settings.

**Step 3: Implement settings and wiring**

Pass the budgets from `LangGraphHostManager` into `HostOrchestrationEngine`; document
them in backend example configuration and Compose.

**Step 4: Update walkthrough and README**

Replace descriptions of one-shot `create_plan()` with `decide_next(state)`, dynamic
rounds, per-round parallelism, checkpoint/resume, and progressive UI events. Retain a
short migration note for historical plan events.

**Step 5: Run focused tests**

```bash
pytest -q tests/backend/test_llm_config.py tests/backend/test_backend_import_mode.py tests/smoke/test_compose_config.py
```

Expected: PASS.

**Step 6: Commit**

Stage only files actually changed in this task, then:

```bash
git commit -m "docs: configure constrained react host"
```

### Task 10: Full verification and nginx regression

**Files:**
- Modify only if a regression exposes a defect, always beginning a new RED/GREEN TDD cycle.

**Step 1: Run backend and runtime regression**

```bash
pytest -q
python -m compileall -q agents backend
```

Expected: all tests PASS and compileall exits 0.

**Step 2: Run frontend regression**

```bash
cd frontend && npm test
cd frontend && npm run build
```

Expected: all tests PASS and Vite build succeeds.

**Step 3: Run configuration and whitespace checks**

```bash
docker compose config
git diff --check
```

Expected: both exit 0.

**Step 4: Run deterministic A2A acceptance regression**

Use stub Agents to execute:

```text
deploy nginx in production, perform security review first, then verify it
```

Assert that a missing namespace produces a Host clarification/stop decision after
the Security observation, without pre-creating Resource Orchestrator or Ops cards.
Run the successful variant with an existing namespace and assert Security -> approved
Resource Orchestrator -> Ops -> Host synthesis.

**Step 5: Optional live MCP smoke test**

Only perform Kubernetes writes when explicitly authorized for the target namespace.
For a read-only live check, verify available Agents and MCP health without creating
resources. Record environment limitations separately from deterministic test results.

**Step 6: Review final diff**

```bash
git status --short
git diff --stat
git log --oneline -12
```

Confirm unrelated dirty-worktree files were neither reverted nor accidentally staged.

