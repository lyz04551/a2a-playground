# Constrained ReAct Host Orchestration Design

## Goal

Replace the Host's one-shot full-DAG planning loop with bounded, stateful ReAct
orchestration. The Host decides the next action from the latest observations,
may delegate one or more independent Agent tasks in parallel, persists the round,
and repeats until it can answer, needs user input or approval, or must stop.

The change preserves the existing boundary:

```text
User -> Host -> A2A specialist Agent -> Kubernetes MCP
```

The Host coordinates Agents but never calls Kubernetes MCP directly. Backend
startup remains independent of any particular Agent, and registered external A2A
Agents remain eligible through the same capability registry.

## Decision

Use constrained ReAct as the default Auto-mode scheduler:

```text
Reason over persisted state
-> choose exactly one Host action
-> execute zero or more Agent tasks
-> persist structured observations
-> reason again
-> complete, clarify, await approval, or stop
```

This is preferred over both alternatives:

- A one-shot DAG cannot naturally introduce a new step after an unexpected live
  observation, such as a missing namespace.
- An unconstrained ReAct loop is difficult to resume, audit, bound, and protect
  from duplicate or unsafe actions.

Fixed workflow/DAG execution may remain as a future explicit mode for standardized
release procedures. It is not part of this change.

## Host Actions

Each decision returns exactly one action:

```text
delegate | clarify | request_approval | complete | stop
```

- `delegate` contains one to three new tasks that can run concurrently in the
  current round. Cross-round ordering is represented by persisted observations,
  not speculative future tasks.
- `clarify` asks one essential question and pauses the Run.
- `request_approval` exposes the pending write operation and pauses the Run.
- `complete` returns a final Host synthesis.
- `stop` returns a terminal explanation when continuation is unsafe or impossible.

The model returns a concise decision reason for observability. Internal hidden
chain-of-thought is neither requested nor stored.

## Persisted Run State

The decision input is a bounded structured snapshot:

```json
{
  "goal": "deploy nginx in production after security review",
  "round": 2,
  "completed_tasks": [],
  "observations": [],
  "pending_approval": null,
  "user_inputs": [],
  "budgets": {
    "max_rounds": 8,
    "max_tasks": 12,
    "max_parallel_tasks": 3
  }
}
```

Every delegated task has a stable ID, Agent ID, objective, risk, required skill
and tags, workflow role, completion criteria, terminal result, and evaluation.
The Run checkpoint stores all completed rounds and the current pause reason.

State supplied to the model is compacted to structured summaries and bounded raw
text excerpts. Full Agent output and tool events remain persisted for display and
audit, but are not repeatedly copied into every decision prompt.

## Round Execution

For each round the engine:

1. Loads available Agent capability profiles and the persisted Run state.
2. Requests the next structured Host decision.
3. Validates the action and every proposed task in deterministic code.
4. Emits a round/decision event and, for `delegate`, incrementally announces only
   the tasks introduced in that round.
5. Runs the round's tasks concurrently through the existing bounded A2A executor.
6. Evaluates and persists each result as an observation.
7. Starts the next decision round only after every task in the current round has
   reached a terminal or approval-required state.

Parallel execution is retained. For example, Security and Capacity checks may be
one `delegate` action with two tasks; resource mutation is considered only in a
later round after both observations exist.

## Deterministic Guardrails

Prompt instructions express policy intent, while code enforces these invariants:

- Only registered and currently available Agents may be selected.
- Required skills, tags, and risk must match the selected Agent capability card.
- Read-only Agents cannot receive write work.
- A Kubernetes mutation requires a successful Security precheck observation for
  the proposed resource configuration.
- A successful mutation must be followed by verification before `complete`, unless
  the Run terminates with an explicit failure or user rejection.
- `continuation.allowed == false` blocks mutation based on that observation.
- Write work cannot execute without the existing approval protocol.
- Stable task fingerprints prevent duplicate semantic work and especially duplicate
  writes across retries, reconnects, and approval resume.
- The engine enforces maximum rounds, total tasks, parallel tasks, attempts, model
  timeouts, and wall-clock cancellation.
- When a budget is exhausted, the Host performs a bounded final synthesis or stops;
  it cannot continue deciding indefinitely.

## Approval and Resume

Approval remains attached to the same child task and remote A2A operation.

When a delegated task returns `approval_required`:

1. Other already-running tasks in the same round may finish and persist results.
2. The Run pauses after the round settles.
3. Approval or rejection is saved in the ReAct checkpoint.
4. Approval resumes the same remote task rather than generating a replacement write.
5. The completed result becomes a new observation.
6. Host reasoning resumes with the next round.

Rejection records a terminal blocked observation. The Host then decides whether to
stop or complete with a partial-result summary; it must not propose the rejected
operation again.

## Decision and Observation Contracts

The initial `HostPlan` becomes a per-round `HostDecision`. A delegate decision uses
the existing `PlannedTask` contract where possible:

```json
{
  "action": "delegate",
  "reason": "Security and capacity checks are independent",
  "tasks": [
    {
      "id": "security-check-1",
      "agent_id": "k8s-security",
      "objective": "Assess the proposed nginx workload",
      "risk": "read",
      "workflow_role": "precheck",
      "required_skill": "kubernetes-security-review",
      "required_tags": ["security"],
      "completion_criteria": ["Return a structured continuation decision"]
    }
  ]
}
```

Specialist observations continue using `SpecialistOutput`. Control flow consumes
terminal state, evaluation, and structured continuation fields; it never derives
write authorization solely from natural-language text.

## Event and UI Contract

The UI appends work progressively instead of displaying speculative future tasks.
Required Host-level events are:

```text
host.round_started
host.decision_created
host.round_completed
host.synthesis_started
```

Existing child lifecycle, message, tool, and approval events remain unchanged.
`host.decision_created` includes the public reason and newly delegated tasks.
Compatibility normalization may continue emitting or accepting `host.plan_created`
while stored historical Runs still contain one-shot plans.

The page shows:

- every Host decision in order;
- each newly introduced Agent card and its live output;
- parallel tasks as members of the same round;
- clarification or approval pauses;
- the final Host synthesis separately from all Agent results.

Reconnect reconstructs the same rounds and cards from persisted events.

## Failure Handling

- One failed parallel task does not discard successful observations from the round.
- Agent replacement is permitted only for a matching capability and only before an
  approved write has begun.
- Malformed model decisions are rejected and retried within a small decision retry
  budget; exhausted retries terminate with a visible Host failure.
- Malformed Agent structured output remains visible but cannot satisfy a guarded
  precheck or authorize continuation.
- An unavailable Agent affects only its delegated task and does not prevent Backend
  startup or unrelated Agents from operating.
- Cancellation prevents new rounds and cancels unfinished local execution without
  erasing persisted observations.

## Compatibility and Migration

- Stable Agent IDs and A2A/MCP interfaces do not change.
- Existing task execution, retry, replacement, progress streaming, and evaluation
  code is reused behind a round executor.
- Historical one-shot DAG events remain readable by the frontend.
- Approval checkpoints accept the previous persisted plan format during migration;
  newly created Auto Runs store ReAct state.
- Direct mode is unchanged.

## Verification

Backend tests must prove:

- The next decision receives prior structured observations.
- A blocking Security result prevents a mutation task from executing and allows the
  Host to clarify, stop, or complete without pre-created blocked/pending cards.
- Independent tasks in one round execute concurrently.
- A later round can introduce a task that was not known in the first round.
- Duplicate task fingerprints and repeated writes are rejected.
- Approval pauses and resumes the same task, then returns to Host reasoning.
- Mutation success cannot complete the Run before an Ops verification observation.
- Round/task budgets terminate loops deterministically.
- Partial failures retain successful results for final synthesis.
- Existing Direct mode and legacy event replay continue to work.

Frontend tests must prove:

- Agent cards appear only when their decision round is created.
- Parallel tasks share a visible round and stream independently.
- Earlier Agent output remains visible after later decisions.
- Approval/reconnect reconstructs the same ReAct checkpoint view.
- Host final synthesis remains separate.

The acceptance regression is:

```text
User: deploy nginx in production after security review and verify it
Round 1: Security (and optional Capacity) observation
Round 2: clarify or request approval if a prerequisite such as namespace creation
         was not part of the original authorized scope
Round 3: Resource Orchestrator mutation after authorization
Round 4: Ops verification
Final: Host synthesis preserving every Agent result
```
