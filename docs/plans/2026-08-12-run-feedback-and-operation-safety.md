# Run Feedback and Operation Safety Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve Run control and connection feedback while making approval and tool details safer.

**Architecture:** Extend the existing Run stream hook with connection lifecycle state, derive cancelability from durable Run status, reuse one approval component, and centralize safe structured-data handling in pure utilities.

**Tech Stack:** React 18, Ant Design 6, browser Fetch/Blob APIs, Node test runner.

---

### Task 1: Run connection lifecycle and durable cancellation

**Files:**
- Modify: `frontend/src/api/runStream.js`
- Modify: `frontend/src/hooks/useRunStream.js`
- Modify: `frontend/src/pages/WorkspacePage.jsx`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`

Expose connecting/reconnecting/recovered/connected/interrupted states. Derive a stop
action from non-terminal durable Run status and make cancellation update visible state.

### Task 2: Approval risk and comparison

**Files:**
- Modify: `frontend/src/components/ApprovalCard.jsx`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`
- Create: `frontend/src/components/workspace/operationSafety.js`
- Test: `frontend/src/components/workspace/operationSafety.test.js`

Compute a flattened field diff against the preceding matching approval, show risk and
digest context, and replace the inline approval markup with the shared card.

### Task 3: Safe tool detail actions

**Files:**
- Modify: `frontend/src/components/workspace/ToolActivity.jsx`
- Modify: `frontend/src/styles/workspace.css`

Render, copy, and download only redacted structured details. Keep raw details collapsed
by default and announce successful actions.

### Task 4: Full regression

Run frontend and backend tests, production build, Python compilation, API route checks,
and `git diff --check`.
