# Sidebar Agent Order Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Place the Agents sidebar entry immediately above Workspace.

**Architecture:** Keep the existing `NAV_ITEMS` configuration and reorder only its entries. This is a static presentation decision, so verify it through the production build and rendered navigation rather than a brittle source-text test.

**Tech Stack:** React 18, Node.js test runner, Vite 5

---

### Task 1: Reorder the sidebar navigation

**Files:**
- Modify: `frontend/src/components/shell/AppShell.jsx`

**Step 1: Record the current rendered order**

Confirm the current sidebar order is:

```text
Dashboard, Workspace, Agents, Events
```

**Step 2: Implement the minimal change**

Move the existing `/agents` entry above the existing `/workspace` entry in `NAV_ITEMS`. Do not change entry contents.

**Step 3: Verify the frontend**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: all tests pass and Vite produces a successful production build.

**Step 4: Visually verify**

Open the local frontend and confirm the desktop sidebar order is Dashboard, Agents, Workspace, Events.
