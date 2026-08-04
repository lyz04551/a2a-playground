# Unified A2A Agent Workspace Design

**Date:** 2026-07-30
**Status:** Approved for planning

## 1. Objective

Evolve the current A2A Playground into one coherent agent workspace that supports:

- direct conversation with one selected A2A Agent;
- automatic multi-agent orchestration through the Host Agent;
- one shared conversation, run, event, approval, and artifact experience;
- a polished operations-console interface that makes agent activity understandable.

The first version intentionally excludes saved teams, user-defined agent groups,
and a visual workflow/DAG editor.

## 2. Current State

The project already contains the essential engineering pieces:

- independent A2A services for Kubernetes operations, orchestration, and security;
- direct single-Agent chat;
- a LangGraph Host that delegates through A2A;
- SSE streaming;
- persisted conversations, runs, events, approvals, and artifacts;
- a policy boundary that requires approval for Kubernetes mutations.

The main limitation is that direct chat and Host orchestration are implemented as
parallel product paths. They use separate pages, endpoints, event handling, and
presentation models. This creates duplicated frontend logic and makes the two modes
feel like separate applications.

## 3. Scope

### 3.1 Included

- One Agent Workspace replacing the separate Chat and Multi-Agent experiences.
- Two execution modes:
  - **Direct:** send the request to one explicitly selected Agent.
  - **Auto:** let the Host select and coordinate one or more Agents.
- A unified run-oriented backend API and event envelope.
- A consistent execution trace for both modes.
- Persisted task hierarchy, approval state, artifacts, and failures.
- Provider/model availability and Agent health indicators.
- Responsive desktop and tablet layouts.
- Compatibility adapters for existing APIs during migration.

### 3.2 Excluded

- Team mode and saved Agent teams.
- User-authored workflow graphs.
- Scheduled workflows.
- Marketplace or remote installation of Agents.
- Multi-user tenancy and role-based access control.
- Billing and detailed token-cost accounting.

## 4. Product Model

The user works in one Workspace and selects a mode for each conversation.

### Direct mode

The user selects a target Agent. The backend creates a Run with one delegated A2A
Task. Tool calls, input-required states, approvals, artifacts, errors, and completion
are represented by the same events used in Auto mode.

### Auto mode

The Host receives the goal, decides whether clarification is needed, selects one or
more registered Agents, delegates through A2A, handles intermediate results, and
produces the final response. The user does not configure an Agent team.

Auto mode may use multiple Agents when the goal requires independent expertise, but
this is an internal Host decision rather than a third user-facing mode.

## 5. User Experience

### 5.1 Information architecture

The primary navigation becomes:

1. **Workspace** — Direct and Auto conversations.
2. **Agents** — registry, capabilities, skills, health, and direct-chat shortcut.
3. **Runs** — searchable run history and execution details.
4. **Settings** — model provider and runtime diagnostics.

The existing Events page is folded into Runs. Raw events remain available in a
developer-oriented detail view.

### 5.2 Workspace layout

Desktop uses three functional regions:

- left: conversations, filters, and new-conversation action;
- center: messages, artifacts, composer, and mode/Agent selection;
- right: execution trace, approval cards, timing, and failures.

The right trace panel is collapsible. On narrower screens, the conversation list and
trace appear as drawers so the message area remains usable.

### 5.3 Mode selection

The composer header contains a two-option segmented control:

- **Direct**
- **Auto**

Direct mode shows a required Agent selector. Auto mode shows the Host identity and
the available Agent count. Changing mode after a conversation has messages creates
a new conversation to preserve run semantics and history clarity.

### 5.4 Message presentation

Messages distinguish:

- the user;
- Host responses;
- delegated Agent responses;
- tool activity;
- system and failure notifications.

Tool activity defaults to a human-readable summary. Raw JSON is available through an
expandable detail section. Messages display source Agent, state, duration, and
artifact count where applicable.

### 5.5 Empty, loading, and error states

- Empty Workspace shows example goals for Direct and Auto modes.
- Planning, delegation, remote execution, and summarization have distinct labels.
- A disconnected model is different from an offline Agent.
- Retriable failures offer Retry; non-retriable failures explain the corrective
  action.
- An interrupted stream can reconnect from the last persisted event cursor.
- Approval-required Runs remain visible and resumable after page refresh.

## 6. Visual System

The interface follows a restrained AI operations-console direction.

### 6.1 Tokens

- Primary: emerald, used for primary actions and successful completion.
- Orchestration: blue, used for Host planning and delegation.
- Approval: amber.
- Failure: red.
- Background: cool neutral gray.
- Surface: white in light mode and layered slate in dark mode.
- Text: high-contrast slate.
- Radius scale: 8, 12, and 16 pixels.
- Spacing scale: 4, 8, 12, 16, 24, 32, and 48 pixels.
- Body type: Inter or the system sans-serif stack.
- Technical type: JetBrains Mono or the system monospace stack.

### 6.2 Component rules

- Cards use borders before shadows; shadows indicate elevation or active work.
- Status is never communicated by color alone.
- Focus indicators are visible for all interactive controls.
- Motion is limited to state transitions and respects reduced-motion preferences.
- Text and controls target WCAG 2.1 AA contrast.
- Inline styles are migrated toward shared component classes and design tokens.

## 7. Unified Runtime Architecture

```text
React Agent Workspace
        |
        | POST /api/runs/stream
        v
Run Service
  |-- Direct Execution Strategy
  |       `-- A2A Gateway --> Selected Agent
  |
  `-- Auto Execution Strategy
          `-- LangGraph Host --> A2A Gateway --> One or more Agents

Run Service --> Repository
            --> Event Stream
            --> Approval Service
            --> Artifact Store
```

Both execution strategies implement the same interface:

```python
class ExecutionStrategy:
    async def execute(self, command: RunCommand) -> AsyncIterator[RunEvent]:
        ...
```

The Run Service owns persistence, event sequencing, cancellation, failure mapping,
and stream lifecycle. Strategies decide only how a request is executed.

## 8. API Design

### 8.1 Start and stream a Run

`POST /api/runs/stream`

```json
{
  "conversation_id": "optional-existing-conversation",
  "mode": "direct",
  "target_agent_id": "k8s-ops",
  "message": "Diagnose the payments namespace"
}
```

For Auto mode, `target_agent_id` is omitted.

The endpoint returns SSE events. The initial event contains the authoritative
conversation and Run IDs.

### 8.2 Event envelope

Every event uses a versioned envelope:

```json
{
  "version": 1,
  "event_id": "evt_...",
  "sequence": 12,
  "run_id": "run_...",
  "conversation_id": "conv_...",
  "task_id": "task_...",
  "parent_task_id": null,
  "type": "task.started",
  "timestamp": "2026-07-30T12:00:00Z",
  "data": {}
}
```

Initial event types:

- `run.started`
- `run.completed`
- `run.failed`
- `run.cancelled`
- `host.planning`
- `task.delegated`
- `task.started`
- `task.status_changed`
- `task.completed`
- `task.failed`
- `message.delta`
- `message.completed`
- `tool.called`
- `tool.completed`
- `approval.required`
- `approval.decided`
- `artifact.created`

Events are append-only and sequence numbers are monotonic within a Run.

### 8.3 Supporting endpoints

- `POST /api/runs/get`
- `POST /api/runs/list`
- `POST /api/runs/cancel`
- `POST /api/runs/events`
- `POST /api/approvals/decide`
- `POST /api/system/status`

The old message and Host endpoints remain temporarily available through adapters,
then become deprecated after the Workspace migration is stable.

## 9. Domain Model

### Conversation

Stores title, selected mode, optional Direct target Agent, timestamps, and messages.

### Run

Represents one user request and its full execution lifecycle. It stores the mode,
status, root task, failure details, and timing.

### Task

Represents Host planning or an A2A delegation. Tasks have stable IDs and optional
parent IDs, enabling a tree even when Auto mode uses multiple Agents.

### Event

An immutable fact belonging to a Run and optionally a Task. Events drive persistence,
SSE streaming, replay, and frontend state reduction.

### Approval

References the exact Task, Agent, tool, arguments, digest, and decision. Approving
resumes the same A2A task. Changed arguments require a new approval.

### Artifact

References its producing Task and includes type, name, media type, metadata, and
content or external storage reference.

## 10. State and Failure Handling

Run states:

```text
queued -> planning -> running
running -> input_required -> running
running -> approval_required -> running
running -> completed | failed | cancelled
```

Task states map A2A protocol states into the local normalized state model while
preserving the original remote state in metadata.

Failure rules:

- model-provider failures are reported as Host failures;
- Agent discovery or transport failures are reported against the affected Task;
- Auto mode may select an alternative Agent only when the Host can explain the
  substitution in the trace;
- partial results remain visible when another Task fails;
- client disconnect does not cancel a Run;
- cancellation is explicit and best-effort across remote A2A tasks;
- internal exceptions are logged with correlation IDs but sanitized before reaching
  the browser.

## 11. Security and Operations

- API keys remain server-side and are never returned by status endpoints.
- System status reports configured/unconfigured rather than secret values.
- All tool approval digests are calculated from canonical arguments.
- A2A Agent URLs are validated to reduce SSRF exposure.
- Run, Task, and event logs share correlation IDs.
- Health checks distinguish HTTP reachability, valid Agent Card, and model readiness.
- Limits are applied to artifact size, tool output size, event payload size, and Run
  duration.

## 12. Frontend Component Boundaries

```text
WorkspacePage
├── ConversationSidebar
├── WorkspaceHeader
│   ├── ModeSwitch
│   ├── AgentSelector
│   └── SystemStatus
├── MessageTimeline
│   ├── UserMessage
│   ├── AgentMessage
│   ├── ToolActivity
│   └── ArtifactPreview
├── Composer
└── RunTracePanel
    ├── TaskTree
    ├── ApprovalCard
    └── RunDiagnostics
```

A shared `useRunStream` hook owns stream parsing, cursor handling, retry behavior,
and dispatch into one `runReducer`. Components render normalized state and do not
interpret backend-specific event variants.

## 13. Migration

### Phase 1: foundation

- Introduce shared frontend tokens and primitives.
- Define the versioned Run event schema.
- Build the shared SSE parser and reducer.
- Add system/model readiness status.

### Phase 2: Workspace

- Create the unified Workspace.
- Implement Direct and Auto mode selection.
- Reuse current endpoints through temporary frontend adapters.
- Consolidate message, tool, approval, artifact, and trace presentation.

### Phase 3: unified backend runtime

- Extract routers from the current monolithic application module.
- Add Run Service and Direct/Auto execution strategies.
- Move persistence and streaming responsibility into Run Service.
- Add task hierarchy, event replay, cancellation, and consistent failures.
- Route Workspace through `/api/runs/stream`.

### Phase 4: cleanup

- Remove duplicate SSE implementations.
- Deprecate and then remove legacy chat/Host endpoints.
- Fold Events into the Runs experience.
- Update documentation and operational checks.

## 14. Testing and Acceptance Criteria

### Backend

- Direct mode creates one Run and one delegated Task.
- Auto mode can delegate sequentially to more than one Agent.
- All persisted events have monotonic sequence numbers.
- Reconnecting with an event cursor does not duplicate events.
- Approval resumes the same task and rejects modified arguments.
- Offline Agents, unavailable models, timeouts, and cancellations map to stable
  error types.
- Legacy endpoints continue to work during the compatibility period.

### Frontend

- A user can start Direct and Auto conversations from the same page.
- Direct mode cannot send until an online Agent is selected.
- Auto mode clearly distinguishes Host and delegated Agent activity.
- Refreshing the page restores messages, trace, artifacts, and pending approvals.
- Streaming reconnect does not duplicate message text or tool calls.
- The layout works at desktop and tablet widths.
- Primary flows are keyboard accessible and meet WCAG AA contrast targets.

### Success criteria

- No duplicated SSE parser between Direct and Auto modes.
- No separate message presentation model for Direct and Auto modes.
- Every user request has a persisted Run.
- Every delegation is visible as a Task in the trace.
- Model-unavailable and Agent-offline failures are distinguishable without reading
  server logs.

## 15. Key Decisions

### ADR-1: Direct and Auto are execution strategies

**Decision:** Model Direct and Auto as strategies behind one Run Service.

**Why:** It preserves the simplicity of direct chat while giving both modes the same
operational semantics and UI.

**Trade-off:** The migration is larger than a visual-only refresh.

### ADR-2: No Team mode

**Decision:** Do not expose Agent teams in the initial Workspace.

**Why:** Auto orchestration can already use multiple Agents. Saved teams introduce
configuration, validation, and lifecycle complexity without being required for the
current Kubernetes use case.

**Trade-off:** Users cannot constrain Auto mode to a curated subset of Agents.

### ADR-3: Append-only events drive UI state

**Decision:** Persist versioned events and derive frontend trace state through a
reducer.

**Why:** This supports stream recovery, auditing, replay, and consistent rendering.

**Trade-off:** Event versioning and migrations require discipline.

### ADR-4: Compatibility before removal

**Decision:** Preserve existing endpoints through adapters until the unified
Workspace and Run API pass acceptance tests.

**Why:** It allows incremental delivery and reduces regression risk.

**Trade-off:** Duplicate paths exist temporarily and must have an explicit removal
milestone.
