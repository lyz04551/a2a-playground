# Observable A2A Kubernetes Workflow Design

## Goal

Implement an observable Host-led Kubernetes multi-Agent workflow in which the Host delegates ordered work over A2A, each specialist Agent operates Kubernetes through MCP, every Agent's output remains visible in the UI, and the Host publishes a separate final synthesis.

The first acceptance scenario is:

1. Security Agent reviews an nginx deployment request.
2. If the review is not blocking, the K8s Resource Orchestrator creates the resources through MCP after formal approval.
3. After the approved operation completes, the Host resumes the original workflow automatically.
4. Ops Agent verifies Pods, events, and logs.
5. Host produces a final summary without replacing any specialist output.

## Responsibility Boundaries

### Host

- Discovers registered local or external A2A Agents from their Agent Cards.
- Creates and validates a bounded task dependency graph.
- Delegates each task over A2A.
- Automatically advances after successful read-only tasks.
- Pauses only for write approval, essential missing input, a blocking finding, cancellation, or failure that cannot be recovered.
- Resumes the same task graph after approval.
- Preserves every delegated task result and produces a separate final synthesis.
- Does not call Kubernetes MCP tools directly.

### Specialist Agents

- Security Agent reviews Kubernetes manifests and live security evidence through MCP.
- K8s Resource Orchestrator manages Kubernetes resource lifecycles through MCP. It does not coordinate other Agents.
- Ops Agent verifies workload health through MCP after a change.
- Other registered A2A Agents can participate when their Agent Card matches a task.

## Planning Model

The Host uses constrained dynamic planning. The model may adapt tasks to the user's request, while code enforces workflow invariants.

For a Kubernetes deployment mutation, the validated task graph must contain:

```text
security-review -> resource-change -> post-change-verification
```

The checks may be omitted only when the user request is read-only or the relevant stage is demonstrably not applicable. Write tasks must target a write-capable Agent, and each planned task must match at least one declared Agent skill or tag.

Tasks without dependencies may execute concurrently. Tasks with dependencies start only after all required predecessors complete successfully. Read-only success advances automatically.

## Execution and Approval State

Each Host Run persists its plan, child tasks, dependency state, remote A2A bindings, approvals, events, and Agent outputs.

Child task states are:

```text
pending -> working -> completed
                   -> approval_required -> working -> completed
                   -> blocked
                   -> failed
                   -> cancelled
```

When a write tool requests approval:

1. The delegated Agent's A2A task enters `input-required`.
2. The Host child task enters `approval_required`.
3. The Host Run pauses without discarding its plan or completed tasks.
4. Approval continues the same remote A2A task and MCP action.
5. The result is attached to the same Host child task.
6. The Host scheduler resumes the persisted graph.
7. Newly ready dependent tasks start automatically.

Rejection marks the write task blocked and prevents dependent verification tasks from running. The Host still produces a final summary of completed and blocked work.

## Result Contract

Every delegated task retains both its streamed presentation and a structured terminal result:

```json
{
  "status": "completed",
  "summary": "Security review passed",
  "findings": [],
  "resources": [],
  "evidence": [],
  "recommendations": [],
  "continuation": {
    "allowed": true,
    "reason": "No blocking security finding"
  },
  "limitations": []
}
```

The Host may use deterministic status and `continuation.allowed` for control flow. It must not infer whether to continue solely from natural-language prose. Raw text remains available for display and backward compatibility.

## Event Contract

Every event has a `run_id`. Delegated Agent events also have a stable Host `task_id`, `parent_task_id`, and `agent_id`.

Required event sequence for each child task:

```text
task.delegated
task.started
message.delta / tool.called / tool.completed / approval.required
message.completed
task.completed | task.blocked | task.failed
```

The Host final synthesis is emitted against the root Host task only after all executable child tasks reach terminal states.

Events and completed messages are persisted before they are streamed to the UI, allowing reconnect and replay without losing earlier Agent output.

## User Interface

The Workspace renders one persistent card per planned Agent task, in plan order. Each card displays:

- Agent name and task objective.
- Pending, running, approval-required, completed, blocked, or failed status.
- Streaming Agent text.
- MCP tool calls and results.
- Approval state and decision.
- Final Agent output.
- Error or blocking reason.

The next card becomes active automatically after its dependencies complete. Previously completed cards remain visible and are not collapsed into the Host answer.

The root Host section displays:

- Initial execution plan.
- Current workflow progress.
- Final synthesis after the workflow reaches a terminal state.

On page reload or SSE reconnect, the UI rebuilds the same task tree from persisted Run events. It does not depend on in-memory component state for completed outputs.

## Legacy API

`/api/runs/stream` is the authoritative Direct and Auto execution API. Legacy `/api/host/send` and `/api/host/send-stream` endpoints must either delegate to the unified Run service or be deprecated; they must not retain a separate single-Agent keyword-routing behavior.

## Failure Handling

- A blocking security result prevents the resource-change task from starting.
- A failed mutation prevents post-change verification from starting.
- An Agent becoming unavailable may trigger replacement only when another healthy Agent declares a matching skill and compatible risk level.
- Exhausted retries produce a visible failed child card and a Host summary of partial results.
- Malformed Agent output is retained as raw text but cannot authorize continuation of a guarded write workflow.
- Cancellation marks unfinished child tasks cancelled and prevents new tasks from starting.
- Missing required user input produces one Host clarification rather than an invalid MCP call.

## Compatibility

- Keep stable Agent IDs, including `k8s-orchestrator`, during the public rename to K8s Resource Orchestrator Agent.
- Continue accepting existing text-only A2A results while adding the structured result contract.
- Backend startup remains independent of local Agent availability.
- External A2A servers can participate through registration and Agent Cards without becoming Backend dependencies.

## Verification

Backend tests must prove:

- The acceptance scenario plans Security, resource change, and Ops verification in dependency order.
- Security output is persisted before the resource task starts.
- Read-only completion automatically advances the graph.
- Approval pauses the Run and preserves completed outputs.
- Approval continuation resumes the same graph and starts Ops verification.
- Rejection or blocking security findings prevent dependent tasks.
- Replacement Agents must match the required skill and risk.
- Host synthesis is separate from every child Agent output.
- SSE reconnect replays all persisted Agent outputs in order.

Frontend tests must prove:

- One result card is rendered per child task.
- Text and MCP activity attach to the correct Agent card.
- Completed cards remain visible while later tasks run.
- Approval state appears on the resource-change card.
- Host final synthesis appears separately after child cards.
- Reloaded event history reconstructs the same workflow view.

An end-to-end test uses stub A2A Agents for Security, Resource Orchestrator, and Ops to execute the complete acceptance sequence without requiring a live Kubernetes cluster. A live MCP smoke test may validate the same flow separately.
