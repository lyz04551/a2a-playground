# Task Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only `/tasks` page that shows Auto Host-to-Agent rounds and Direct Agent task flows with complete tool, approval, result, and event details.

**Architecture:** Reuse existing run APIs and replay persisted events through `runEvents`. A small pure view-model module converts normalized state into filterable run summaries and flow nodes; React components only render that model.

**Tech Stack:** React 18, React Router, Ant Design, Vite, Node test runner.

---

### Task 1: Task Explorer view model

**Files:**
- Create: `frontend/src/state/taskExplorer.js`
- Test: `frontend/src/state/taskExplorer.test.js`

1. Add failing tests for filtering Runs, Auto round hierarchy, Direct root ownership, tool/approval nodes, and summary statistics.
2. Run `npm --prefix frontend test` and confirm failure.
3. Implement pure model builders using normalized Run state.
4. Run tests and commit.

### Task 2: Page and detail components

**Files:**
- Create: `frontend/src/pages/TasksPage.jsx`
- Create: `frontend/src/components/tasks/TaskRunList.jsx`
- Create: `frontend/src/components/tasks/TaskFlow.jsx`
- Create: `frontend/src/components/tasks/TaskNodeDrawer.jsx`
- Create: `frontend/src/styles/tasks.css`
- Test: `frontend/src/components/taskExplorerLayout.test.js`

1. Add failing layout tests for bounded columns, wrapping, scrolling, and responsive behavior.
2. Implement Run loading, selection, filters, flow rendering, node selection, loading/error/empty states, and lightweight refresh for active Runs.
3. Run tests and commit.

### Task 3: Navigation and deep links

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/shell/AppShell.jsx`
- Modify: `frontend/src/components/shell/CommandPalette.jsx`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`

1. Add `/tasks`, navigation and command palette entries.
2. Add Workspace link `/tasks?run=<id>`.
3. Verify Direct does not render Host and Auto preserves Host rounds.
4. Run all frontend tests and production build.
5. Commit.
