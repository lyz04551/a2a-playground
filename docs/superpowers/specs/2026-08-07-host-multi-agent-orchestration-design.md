# Host Multi-Agent Orchestration Design

## 1. Background

The current Host Agent behaves primarily as a smart router: it selects an Agent, calls `send_task`, and summarizes that Agent's response. The existing Run, Task, and Event model can already record more than one delegation, but the Host has no explicit plan, dependency graph, result-evaluation step, or reliable retry and replanning behavior.

This design upgrades the Host from a single-Agent router into a controlled multi-Agent orchestrator while preserving the fast path for simple requests.

## 2. Goals

- Automatically decide whether a request needs one Agent or several Agents.
- Decompose complex requests into auditable sub-tasks.
- Support parallel work for independent sub-tasks and serial work when one result feeds another.
- Pass only the necessary output of predecessor tasks to dependent Agents.
- Evaluate whether collected results satisfy the user's request before answering.
- Retry transient failures once, then replan to another suitable Agent when possible.
- Preserve useful partial results and report unresolved portions honestly.
- Keep all mutating operations behind the existing approval flow.
- Give LangGraph and ADK Hosts the same orchestration semantics.
- Expose planning, delegation, retry, replanning, approval, and synthesis through Run events.

## 3. Non-goals

- Allowing registered Agents to call each other freely.
- Building an unrestricted recursive Agent network.
- Automatically bypassing approval because another Agent recommended a mutation.
- Introducing a distributed workflow engine or durable cross-process job queue in this iteration.
- Replacing the existing A2A gateway, persistence layer, or frontend Run model.

## 4. Chosen Architecture

Use a hybrid architecture: the language model performs semantic planning and result evaluation, while deterministic backend code validates and executes the plan.

The orchestration lifecycle is:

1. **Analyze** — determine scope, risk, and whether the single-Agent fast path is sufficient.
2. **Plan** — produce a structured plan containing sub-tasks and dependencies.
3. **Schedule** — validate the plan and execute ready sub-tasks, concurrently where safe.
4. **Evaluate** — determine whether results meet the requested outcome and each sub-task's completion criteria.
5. **Synthesize** — produce one coherent user-facing response with completed work, evidence, and unresolved items.

The Host remains the only coordinator. Registered Agents receive bounded task prompts and do not gain direct access to other Agents.

## 5. Core Components

### 5.1 Capability Registry

Agent registration is normalized into a capability profile. Each profile contains:

- stable Agent ID and display name;
- description and Agent Card endpoint;
- skills with IDs, descriptions, tags, and examples;
- supported input and output modes;
- risk level and whether the Agent is read-only;
- operational limits and unsuitable scenarios;
- health and availability;
- optional priority used only as a deterministic tie-breaker.

The registry exposes capability matching rather than name-based matching. Candidate ranking considers skill match, risk compatibility, health, and declared limitations. Offline Agents are excluded.

The three bundled Agents retain clear roles:

- `k8s-ops`: read-only diagnosis, logs, events, health, and resource inspection;
- `k8s-security`: read-only security, RBAC, network, image, and policy assessment;
- `k8s-orchestrator`: change planning and approved mutations.

### 5.2 Structured Plan

The planner returns a validated object with this logical shape:

```json
{
  "summary": "Short statement of the intended outcome",
  "tasks": [
    {
      "id": "diagnose",
      "agent_id": "k8s-ops",
      "objective": "Identify the cause of the failed rollout",
      "input": "User request and relevant known context",
      "depends_on": [],
      "completion_criteria": ["Root cause supported by observable evidence"],
      "risk": "read",
      "max_attempts": 2
    }
  ]
}
```

Validation rejects unknown Agents, duplicate task IDs, dependency cycles, missing dependencies, unsupported capabilities, and mutation tasks assigned to read-only Agents. Plan size is bounded to avoid runaway decomposition. The initial limit is six sub-tasks and two attempts per sub-task, including the first attempt.

A simple request still produces a one-node plan internally. The frontend may present it as a direct delegation to avoid unnecessary visual noise.

### 5.3 Scheduler

The scheduler computes ready tasks from the dependency graph:

- tasks with no unmet dependencies may run concurrently;
- dependent tasks start only after all required predecessors complete;
- a dependent task receives a compact, labeled context package derived from predecessor results;
- no task may create additional tasks directly;
- write-risk tasks stop at approval and resume through the existing approval mechanism.

Concurrency is bounded by a configurable limit, initially three. The scheduler owns task status transitions and cancellation propagation.

### 5.4 Context Builder

The context builder creates each Agent prompt from:

- the sub-task objective and completion criteria;
- the relevant portion of the original user request;
- selected predecessor findings labeled by source task and Agent;
- applicable constraints, including read-only or approval requirements;
- an explicit response contract requesting findings, evidence, uncertainty, and recommended next steps.

Raw conversation history and unrelated Agent output are not forwarded. Large predecessor outputs are summarized, with references to the originating task retained for traceability.

### 5.5 Result Evaluator and Replanner

Each result is evaluated against the task's completion criteria. Outcomes are:

- `sufficient`: task completes;
- `insufficient`: retry with clearer context if attempts remain;
- `failed`: retry once for a transient failure;
- `blocked`: approval or missing user input is required.

After the second unsuccessful attempt, the Host searches for another compatible Agent. If one exists, it replaces the failed plan node and records a replan event. If no substitute exists, dependent tasks that cannot proceed are marked blocked, independent completed results are retained, and synthesis reports the partial outcome.

Replanning cannot change a read task into a write task, expand the requested scope, or bypass approval.

### 5.6 Synthesizer

The synthesizer receives the plan and normalized task results, not an unstructured transcript. Its response must:

- answer the original request directly;
- reconcile conflicting findings or state the conflict explicitly;
- distinguish observed facts from recommendations;
- identify which Agents contributed when useful;
- report failed or blocked portions;
- never claim that an approved operation executed until execution evidence exists.

Agent responses are intermediate artifacts. They are not emitted verbatim as the final Host response.

## 6. Shared Host Interface

LangGraph and ADK integrations use a common orchestration service rather than maintaining separate planning prompts and tool semantics.

The shared interface provides:

- list and rank Agent capabilities;
- create and validate a plan;
- execute one bounded sub-task through the A2A gateway;
- evaluate and normalize results;
- synthesize the final response.

Framework-specific managers remain responsible only for adapting model/tool events into the common Host event stream. Stable Agent IDs are used everywhere; ADK's current display-name routing is migrated to stable IDs.

The existing `send_task` tool remains available as the low-level delegation primitive. It is no longer the orchestration policy itself.

## 7. Run, Task, and Event Model

The existing root task represents the Host orchestration. Each plan node becomes a child task. Retries are attempts of the same child task rather than new logical tasks; replacement by another Agent is recorded in task metadata and a replanning event.

Add or standardize events for:

- Host plan created and validated;
- child task ready, delegated, started, completed, failed, or blocked;
- dependency context prepared;
- retry scheduled;
- plan revised and Agent replaced;
- approval required and resumed;
- result evaluation completed;
- final synthesis started and completed.

Every event includes the Run ID, logical task ID, parent task ID, Agent ID where applicable, sequence number, and safe metadata. Sensitive tool output is not copied into event metadata.

The event adapter remains backward compatible with existing `HOST_PLANNING`, `TASK_DELEGATED`, tool, message, approval, and terminal events. New event types enhance the trace without changing direct mode.

## 8. Failure, Cancellation, and Approval

- A transient Agent or gateway failure gets one retry.
- An inadequate response gets one refined attempt.
- After attempts are exhausted, the Host tries one compatible replacement Agent.
- Failure of one independent branch does not cancel successful branches.
- Failure of a required predecessor blocks only its dependent descendants.
- User cancellation stops active child tasks where supported and prevents new tasks from starting.
- Approval pauses the affected write task and any descendants that depend on it; unrelated read-only branches may finish.
- Rejected approval produces a valid partial result, not a fabricated execution failure.
- The Run is `completed` only when synthesis truthfully represents all terminal task states. It is `failed` when no meaningful answer can be produced because the root orchestration itself failed. It remains `approval_required` while user approval is outstanding.

## 9. Frontend Behavior

The multi-Agent trace displays:

- the Host plan as a small dependency graph or ordered task list;
- parallel branches and dependency links;
- the selected Agent and reason for each assignment;
- current attempt, retries, and replacements;
- approval pauses;
- per-task status and concise result summaries;
- final synthesis as the primary conversation response.

Simple one-Agent requests keep the compact current presentation. The UI does not expose raw hidden prompts or sensitive tool payloads.

## 10. Compatibility and Migration

- Direct mode is unchanged and continues to target exactly one selected Agent.
- Auto mode adopts structured orchestration.
- Existing registered Agent records are normalized with conservative defaults when new capability fields are absent.
- Existing Agent YAML files are extended without invalidating current fields.
- Existing Run histories remain readable; new fields and event types are additive.
- LangGraph is implemented first against the shared service; ADK then consumes the same service and stable-ID contract.

## 11. Testing Strategy

Use test-driven development for each behavior. Required coverage includes:

- simple requests take the one-Agent fast path;
- complex requests create valid multi-node plans;
- independent tasks execute concurrently within the limit;
- dependent tasks wait and receive only relevant predecessor context;
- invalid, cyclic, oversized, or capability-incompatible plans are rejected;
- transient failure retries once;
- insufficient results trigger a refined retry;
- exhausted attempts trigger a compatible Agent replacement;
- unavailable replacements yield an honest partial synthesis;
- mutations cannot be assigned to read-only Agents;
- approval pauses and resumes the correct task and descendants;
- cancellation prevents further scheduling;
- conflicting Agent findings are surfaced in synthesis;
- LangGraph and ADK adapters emit equivalent normalized events;
- old Agent registrations and Run histories remain compatible;
- frontend state renders single, parallel, serial, retry, replan, approval, and partial-failure traces.

## 12. Rollout Sequence

1. Define plan, capability, result, and event contracts with unit tests.
2. Extend Agent registration metadata and bundled Agent YAML files.
3. Implement plan validation, dependency scheduling, bounded concurrency, and context building.
4. Add evaluation, retry, replacement, and partial-result semantics.
5. Integrate the shared service with LangGraph Host.
6. Update Run persistence and event normalization.
7. Update the frontend orchestration trace.
8. Migrate ADK Host to the shared service and stable Agent IDs.
9. Run backend, runtime, Agent-card, frontend-state, and smoke regression suites.

## 13. Acceptance Criteria

The optimization is accepted when:

- a simple diagnostic request delegates once and returns a synthesized answer;
- a request needing diagnosis and security review runs both read-only Agents concurrently;
- a request needing diagnosis followed by remediation passes the diagnosis into the remediation plan and pauses before mutation;
- Agent failure produces one retry and then a safe replacement or explicit partial result;
- the UI and persisted event stream show why each Agent ran and how results were combined;
- no path permits an unapproved mutation;
- both Host framework adapters follow the same stable-ID and orchestration contracts;
- all relevant automated tests and builds pass.
