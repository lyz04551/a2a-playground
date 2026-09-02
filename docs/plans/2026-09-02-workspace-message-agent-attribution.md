# Workspace Message Agent Attribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show the concrete child Agent name for child-task messages and “Host Agent 总结” for Host root summaries in the workspace conversation.

**Architecture:** The run-event reducer will persist source identity (`agentId`, `agentName`, `source`) on each normalized message, inheriting identity from its task when the message event omits it. A small presentation helper will resolve registered Agent names and localized Host labels before `MessageTimeline` renders them, while retaining a generic fallback for legacy messages.

**Tech Stack:** React, JavaScript, Node test runner, Vite

---

### Task 1: Preserve message source during event reduction

**Files:**
- Modify: `frontend/src/state/runEvents.js`
- Test: `frontend/src/state/runEvents.test.js`

**Step 1: Write the failing tests**

Add assertions that a child-task message keeps its event or task `agent_id`, and that a root message is marked with `source: 'host'`.

**Step 2: Run the focused test to verify it fails**

Run: `node --test frontend/src/state/runEvents.test.js`

Expected: FAIL because normalized messages do not yet contain source identity.

**Step 3: Implement minimal source normalization**

In the message event branch, derive the task first, then add:

```js
const agentId = data.agent_id || current?.agentId || task?.agentId || ''
const source = event.parent_task_id === null ? 'host' : 'agent'
```

Persist `agentId`, available `agentName`, and `source` on the upserted message without erasing identity on later delta/completed events.

**Step 4: Run the focused test**

Run: `node --test frontend/src/state/runEvents.test.js`

Expected: PASS.

### Task 2: Resolve and render readable source names

**Files:**
- Modify: `frontend/src/components/workspace/workspaceState.js`
- Modify: `frontend/src/pages/WorkspacePage.jsx`
- Modify: `frontend/src/components/workspace/MessageTimeline.jsx`
- Test: `frontend/src/components/workspaceState.test.js`

**Step 1: Write the failing helper tests**

Cover child Agent registry lookup, unknown Agent ID fallback, localized Host summary label, user label, and generic legacy fallback.

**Step 2: Run the focused test to verify it fails**

Run: `node --test frontend/src/components/workspaceState.test.js`

Expected: FAIL because the message enrichment helper does not exist.

**Step 3: Implement minimal presentation helper**

Add a pure helper that returns messages with `agentName` resolved by role/source/Agent registry. Use it from `WorkspacePage` with `useMemo`, pass the enriched messages to `MessageTimeline`, and let `MessageTimeline` retain “Agent” only as its final compatibility fallback.

**Step 4: Run focused tests**

Run: `node --test frontend/src/components/workspaceState.test.js frontend/src/state/runEvents.test.js`

Expected: PASS.

### Task 3: Verify and commit

**Files:**
- Verify all modified frontend files

**Step 1: Run the full frontend test suite**

Run: `npm --prefix frontend test`

Expected: all tests pass.

**Step 2: Build the production frontend**

Run: `npm --prefix frontend run build`

Expected: Vite build succeeds; the existing chunk-size warning is acceptable.

**Step 3: Check the patch**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only scoped files changed.

**Step 4: Commit**

```bash
git add frontend/src/state/runEvents.js frontend/src/state/runEvents.test.js frontend/src/components/workspace/workspaceState.js frontend/src/components/workspaceState.test.js frontend/src/components/workspace/MessageTimeline.jsx frontend/src/pages/WorkspacePage.jsx docs/plans/2026-09-02-workspace-message-agent-attribution.md
git commit -m "fix: label workspace messages by agent"
```
