# A2A Playground Frontend Console Phase One Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a cohesive, responsive operations console with a dashboard, persisted display settings, global command search, improved Workspace interactions, run debugging, and consistent Agents and Events pages.

**Architecture:** Keep the existing React/Vite/Ant Design application and API contracts. Add small pure state modules for settings and search, a shared application shell, and page-level components that consume existing APIs; keep SSE normalization inside the existing run hook and expose raw events to both the trace and debugger.

**Tech Stack:** React 18, React Router 6, Ant Design 6, Vite 5, CSS custom properties, Node test runner.

---

### Task 1: Establish testable console settings and design tokens

**Files:**
- Create: `frontend/src/state/consoleSettings.js`
- Create: `frontend/src/state/consoleSettings.test.js`
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/index.css`

**Step 1: Write the failing settings tests**

Test default normalization, invalid stored values, and serialization:

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_SETTINGS, normalizeSettings, serializeSettings } from './consoleSettings.js'

test('normalizes persisted console settings', () => {
  assert.deepEqual(normalizeSettings({ theme: 'dark', density: 'compact' }), {
    ...DEFAULT_SETTINGS, theme: 'dark', density: 'compact',
  })
  assert.equal(normalizeSettings({ theme: 'neon' }).theme, 'light')
})

test('serializes only supported settings', () => {
  assert.equal(JSON.parse(serializeSettings({ ...DEFAULT_SETTINGS, extra: true })).extra, undefined)
})
```

**Step 2: Run the test and verify failure**

Run: `cd frontend && node --test src/state/consoleSettings.test.js`

Expected: FAIL because `consoleSettings.js` does not exist.

**Step 3: Implement the pure settings module**

Export `DEFAULT_SETTINGS`, `normalizeSettings`, `parseSettings`, and `serializeSettings`. Supported values are `light|dark`, `comfortable|compact`, `zh-CN|en-US`, plus boolean `sidebarCollapsed` and `onboardingComplete`.

**Step 4: Define the visual system**

Replace OS-driven dark mode in `tokens.css` with `[data-theme="dark"]`; add typography, shell dimensions, focus, surface, overlay, success/warning/danger, and compact-density variables. In `index.css`, add global resets, selection, scrollbar, motion-reduction, focus-visible, and reusable console page/card/header classes. Do not use remote fonts.

**Step 5: Verify tests and build**

Run: `cd frontend && npm test && npm run build`

Expected: all Node tests pass and Vite build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/state/consoleSettings.js frontend/src/state/consoleSettings.test.js frontend/src/styles/tokens.css frontend/src/index.css
git commit -m "feat: add console settings and design tokens"
```

### Task 2: Build the shared responsive application shell

**Files:**
- Create: `frontend/src/context/ConsoleSettingsContext.jsx`
- Create: `frontend/src/components/shell/AppShell.jsx`
- Create: `frontend/src/components/shell/SettingsDrawer.jsx`
- Create: `frontend/src/styles/shell.css`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/main.jsx`

**Step 1: Add a settings provider**

Read settings once from `localStorage` with a guarded parser, persist changes, and apply `data-theme`, `data-density`, and `lang` to `document.documentElement`. Export `useConsoleSettings()` with `settings`, `updateSettings`, and `resetSettings`.

**Step 2: Replace the fixed inline-styled shell**

Move navigation into `AppShell`, add Dashboard to the nav, support collapse, responsive drawer navigation, page title, system indicator, command trigger, theme shortcut, and settings trigger. Use CSS classes instead of inline layout styles.

**Step 3: Connect Ant Design theme tokens**

Generate `ConfigProvider` tokens from the active theme and density. Keep semantic colors aligned with CSS variables and set `algorithm` to Ant Design light/dark algorithms.

**Step 4: Add settings controls**

Create radio/switch controls for theme, density, language, and sidebar behavior. Chinese is the default. Keep the language switch functional for shell labels; page-level translation is completed incrementally in later tasks.

**Step 5: Verify navigation and build**

Run: `cd frontend && npm test && npm run build`

Expected: tests pass; routes render through `AppShell`; build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/context frontend/src/components/shell frontend/src/styles/shell.css frontend/src/App.jsx frontend/src/main.jsx
git commit -m "feat: add responsive console shell"
```

### Task 3: Add Dashboard and first-use guidance

**Files:**
- Create: `frontend/src/pages/DashboardPage.jsx`
- Create: `frontend/src/components/OnboardingPanel.jsx`
- Create: `frontend/src/components/PromptTemplates.jsx`
- Create: `frontend/src/data/promptTemplates.js`
- Create: `frontend/src/styles/dashboard.css`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/main.jsx`

**Step 1: Define prompt templates as data**

Create stable template IDs and Chinese/English labels for cluster health, abnormal Pod analysis, security scan, event triage, and deployment review. Each entry contains only `id`, `title`, `description`, `prompt`, `icon`, and `category`.

**Step 2: Implement Dashboard data loading**

Load `listAgents`, `checkAgentsHealth`, `getSystemStatus`, `listConversations`, `listRuns`, and `listApprovals` using `Promise.allSettled`. Show real totals, recent items, and pending approvals; mark unavailable sections as degraded rather than failing the page.

**Step 3: Implement onboarding**

Derive steps from actual data: model configured, at least one Agent registered, at least one Agent online, and first conversation created. Allow dismissing through `onboardingComplete`, with a settings action to restore it.

**Step 4: Connect template actions**

Selecting a template navigates to `/workspace?mode=auto&prompt=<encoded prompt>`; Workspace will consume it in Task 5. Never execute a prompt directly from Dashboard.

**Step 5: Verify responsive states**

Check full data, partial API failure, no Agents, unconfigured model, and narrow viewport. Run `cd frontend && npm run build`.

Expected: Dashboard remains usable in every state and build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/pages/DashboardPage.jsx frontend/src/components/OnboardingPanel.jsx frontend/src/components/PromptTemplates.jsx frontend/src/data/promptTemplates.js frontend/src/styles/dashboard.css frontend/src/App.jsx frontend/src/main.jsx
git commit -m "feat: add operations dashboard and onboarding"
```

### Task 4: Add global command search

**Files:**
- Create: `frontend/src/state/commandSearch.js`
- Create: `frontend/src/state/commandSearch.test.js`
- Create: `frontend/src/components/shell/CommandPalette.jsx`
- Modify: `frontend/src/components/shell/AppShell.jsx`
- Modify: `frontend/src/styles/shell.css`

**Step 1: Write failing search tests**

Cover case-insensitive matching, weighted title matches, type filtering, empty query defaults, and a maximum result count.

```js
test('ranks title matches before metadata matches', () => {
  const results = searchCommands([
    { id: '1', title: 'Events', keywords: ['agent'] },
    { id: '2', title: 'Agent Ops', keywords: [] },
  ], 'agent')
  assert.equal(results[0].id, '2')
})
```

**Step 2: Verify failure**

Run: `cd frontend && node --test src/state/commandSearch.test.js`

Expected: FAIL because the module does not exist.

**Step 3: Implement search and data adapters**

Create pure `searchCommands`. In `CommandPalette`, load Agents, conversations, and events only when opened, combine them with static navigation/actions, and display a recoverable warning if one source fails.

**Step 4: Implement keyboard and accessibility behavior**

Open on `Meta+K` or `Ctrl+K`, close on Escape, autofocus input, support arrows and Enter, restore focus to the trigger, and expose dialog/listbox roles. Avoid intercepting browser shortcuts other than exact K.

**Step 5: Verify**

Run: `cd frontend && npm test && npm run build`

Expected: search tests pass and build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/state/commandSearch.js frontend/src/state/commandSearch.test.js frontend/src/components/shell/CommandPalette.jsx frontend/src/components/shell/AppShell.jsx frontend/src/styles/shell.css
git commit -m "feat: add global command palette"
```

### Task 5: Improve Workspace conversations, messages, and prompts

**Files:**
- Modify: `frontend/src/pages/WorkspacePage.jsx`
- Modify: `frontend/src/components/workspace/MessageTimeline.jsx`
- Modify: `frontend/src/components/workspace/ModeSwitch.jsx`
- Modify: `frontend/src/styles/workspace.css`
- Create: `frontend/src/components/workspace/ConversationSidebar.jsx`
- Create: `frontend/src/components/workspace/MessageActions.jsx`

**Step 1: Extract the conversation sidebar**

Move the inline component into `ConversationSidebar`. Add local keyword filtering, inline rename using `api.updateConversation`, existing delete confirmation, active state, and clear loading/error/empty states. Refresh conversations after rename, delete, create, restore, and completed sends.

**Step 2: Add message copy actions**

Show actions on focus/hover. Copy plain message content through `navigator.clipboard.writeText`; report success/failure through Ant Design message feedback. Do not add regenerate or edit-and-resend in phase one.

**Step 3: Add prompt templates to the composer**

Render compact template chips above an empty composer. Clicking fills the draft without sending. Read a `prompt` query parameter once, populate the draft, then remove it with `navigate(..., { replace: true })` to prevent replay.

**Step 4: Localize and refine responsive layout**

Use settings language for newly touched Workspace labels. Keep conversations and trace in drawers below their desktop breakpoints; preserve composer access at phone widths.

**Step 5: Verify behavior**

Run: `cd frontend && npm test && npm run build`

Manually verify: search, rename, delete, copy, template fill, Dashboard deep-link, direct/auto mode, SSE cancel, desktop and phone drawers.

**Step 6: Commit**

```bash
git add frontend/src/pages/WorkspacePage.jsx frontend/src/components/workspace frontend/src/styles/workspace.css
git commit -m "feat: improve workspace conversation experience"
```

### Task 6: Add run visualization and debug drawer

**Files:**
- Modify: `frontend/src/hooks/useRunStream.js`
- Modify: `frontend/src/state/runEvents.js`
- Modify: `frontend/src/state/runEvents.test.js`
- Modify: `frontend/src/components/workspace/RunTracePanel.jsx`
- Create: `frontend/src/components/workspace/DebugDrawer.jsx`
- Create: `frontend/src/components/workspace/RunTimeline.jsx`
- Modify: `frontend/src/pages/WorkspacePage.jsx`
- Modify: `frontend/src/styles/workspace.css`

**Step 1: Write failing reducer tests**

Add cases proving raw events retain sequence and timestamp, task start/end derives duration when timestamps exist, failed nodes keep error data, and an interrupted stream retains completed tasks.

**Step 2: Run reducer tests and verify failure**

Run: `cd frontend && node --test src/state/runEvents.test.js`

Expected: new assertions fail against the existing reducer.

**Step 3: Extend run state without changing SSE parsing ownership**

Store a bounded ordered `rawEvents` array in the reducer, with normalized timestamp/sequence. Derive display duration from real event times only; show an em dash when unavailable. Preserve existing task/approval/artifact behavior.

**Step 4: Build the visual timeline**

Render Host → Agent → Tool → Result nodes using normalized events, semantic status icons, active-node animation respecting reduced motion, duration, error summary, and approval placement.

**Step 5: Build the debug drawer**

Display Run ID/Task ID, request metadata available in state, raw event count, elapsed time, Token value or “暂无数据”, and formatted JSON. Add copy-current and copy-all actions with feedback.

**Step 6: Verify**

Run: `cd frontend && npm test && npm run build`

Manually verify completed, failed, waiting approval, cancelled, and disconnected streams.

**Step 7: Commit**

```bash
git add frontend/src/hooks/useRunStream.js frontend/src/state/runEvents.js frontend/src/state/runEvents.test.js frontend/src/components/workspace frontend/src/pages/WorkspacePage.jsx frontend/src/styles/workspace.css
git commit -m "feat: visualize runs and expose debug events"
```

### Task 7: Unify Agents and Events pages

**Files:**
- Modify: `frontend/src/pages/AgentsPage.jsx`
- Modify: `frontend/src/pages/EventsPage.jsx`
- Create: `frontend/src/components/EventDetailDrawer.jsx`
- Create: `frontend/src/styles/agents.css`
- Create: `frontend/src/styles/events.css`
- Modify: `frontend/src/main.jsx`

**Step 1: Restyle Agents using shared console primitives**

Replace inline page layout with classes. Preserve registration, health refresh, search, pagination, chat, and delete behavior. Present only actual online state, capabilities, URL, skills, and health error; do not invent latency or success rate.

**Step 2: Restyle Events and add event details**

Use shared headers, metric cards, semantic status badges, and filters. Clicking an event opens `EventDetailDrawer` with identifiers, timestamps, state, tool/agent information, and formatted raw JSON.

**Step 3: Add JSON copy behavior**

Use guarded Clipboard API handling with visible success/error feedback. Ensure drawer content remains readable in dark and compact modes.

**Step 4: Verify**

Run: `cd frontend && npm test && npm run build`

Manually verify Agent registration modal, health refresh, pagination, deletion, event filters, detail drawer, and copy JSON.

**Step 5: Commit**

```bash
git add frontend/src/pages/AgentsPage.jsx frontend/src/pages/EventsPage.jsx frontend/src/components/EventDetailDrawer.jsx frontend/src/styles/agents.css frontend/src/styles/events.css frontend/src/main.jsx
git commit -m "feat: unify agent and event operations pages"
```

### Task 8: Final integration, responsive QA, and documentation

**Files:**
- Modify: `README.md`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/dashboard.css`
- Modify: `frontend/src/styles/workspace.css`
- Modify: `frontend/src/styles/agents.css`
- Modify: `frontend/src/styles/events.css`

**Step 1: Run the complete automated verification**

Run: `cd frontend && npm test && npm run build`

Expected: every Node test passes and Vite exits successfully with production assets.

**Step 2: Run the app and perform visual QA**

Run: `cd frontend && npm run dev -- --host 127.0.0.1`

Check Dashboard, Workspace, Agents, Events, command palette, settings, onboarding, and drawers at approximately 1440 px, 1024 px, 768 px, and 390 px. Check light/dark and comfortable/compact combinations. Fix overflow, contrast, focus, and sticky composer issues found during inspection.

**Step 3: Perform accessibility and resilience checks**

Navigate shell, command palette, settings, messages, and drawers using the keyboard. Enable reduced motion. Simulate one failed Dashboard API, offline Agents, empty data, and SSE interruption; confirm useful fallback states remain.

**Step 4: Update README**

Document the Dashboard, `Command/Ctrl+K`, display settings, prompt templates, debug drawer, responsive navigation, and the fact that Token/advanced analytics require future backend support.

**Step 5: Review the diff boundary**

Run: `git status --short && git diff --check`

Expected: no whitespace errors; unrelated pre-existing user changes remain untouched and unstaged.

**Step 6: Commit**

```bash
git add README.md frontend/src/styles
git commit -m "docs: document frontend console experience"
```

**Step 7: Final verification record**

Record the exact `npm test` and `npm run build` results in the delivery message, plus any visual QA limitations. Do not claim Token statistics, server-side search, favorites, pinning, regenerate, or historical analytics were implemented.
