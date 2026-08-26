# Agent Task Details Design

## Goal

Make every Agent task in the right-side Run trace clickable so users can see which Agent handled it, what Host asked it to do, its dependencies, execution state, retries, and returned result.

## Interaction

- Agent rows are keyboard-accessible buttons.
- Selecting a row opens an Ant Design Drawer without leaving the workspace.
- The selected row is visually highlighted.
- The Drawer shows Agent identity, objective, original task input, status, elapsed time, dependencies, completion criteria, attempt/replacement history, result, and failure/block/approval reason.
- Missing results show an explicit state-specific message instead of `—`.
- Parallel tasks are labeled when they have the same dependency readiness level; dependent tasks list their predecessor names.
- Host synthesis stays in the main conversation.

## Data Flow

`host.plan_created` seeds task objectives, inputs, dependencies, criteria, and Agent IDs. Lifecycle events update attempts, replacement, status, timestamps, and results. `adaptRunStateForLegacy` carries this normalized information into the current trace component. Old Runs without plan metadata remain clickable and show the fields that are available.

## Safety and Stale Runs

The Drawer distinguishes working, completed, failed, blocked, approval-required, and cancelled states. It shows the most recent event time so a persisted stale Run is not presented as proof of active work. This UI does not automatically cancel Runs.

## Testing

- Reducer tests verify plan metadata and task results survive normalization.
- Pure view-model tests verify labels, missing-result text, dependency names, replacement history, and legacy fallback.
- Frontend build verifies Drawer integration.

## Acceptance Criteria

- Clicking any Agent task opens its details.
- Ops and Security tasks show distinct objectives and results.
- Dependent synthesis tasks show both predecessor tasks.
- Completed tasks show full Agent output.
- Failed, blocked, approval, cancelled, and missing-result states are explicit.
- Keyboard activation and close behavior work.
