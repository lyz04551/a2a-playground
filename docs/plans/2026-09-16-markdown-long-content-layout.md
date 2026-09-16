# Markdown Long Content Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent long inline Markdown code and identifiers from widening or being clipped inside Agent message cards.

**Architecture:** Keep the fix in the shared Markdown and workspace layout CSS. Add selector-level regression assertions before changing production styles, preserve independent scrolling for fenced code blocks and tables, then verify with the full frontend test suite, production build, and a browser screenshot.

**Tech Stack:** React, react-markdown, CSS, Node test runner, Vite, Playwright CLI.

---

### Task 1: Add the layout regression test

**Files:**
- Modify: `frontend/src/components/markdownLayout.test.js`

1. Assert that `.markdown-content code` allows long tokens to wrap.
2. Assert that `.markdown-content pre code` restores code-block whitespace behavior.
3. Assert that the workspace message and Markdown content containers can shrink to their parent width.
4. Run `npm test -- src/components/markdownLayout.test.js` from `frontend` and confirm the new assertions fail for the missing CSS declarations.

### Task 2: Implement the minimal CSS fix

**Files:**
- Modify: `frontend/src/styles/markdown.css`
- Modify: `frontend/src/styles/workspace.css`

1. Add `max-width: 100%` and shrink constraints to shared Markdown and message containers.
2. Add wrapping rules to inline `code`.
3. Override those rules for `pre code` so fenced code blocks retain preformatted content and their existing horizontal scrollbar.
4. Re-run the focused test and confirm it passes.

### Task 3: Verify the complete frontend

**Files:**
- No production changes expected.

1. Run `npm test` from `frontend`.
2. Run `npm run build` from `frontend`.
3. Render a representative long Markdown message in the browser and confirm there is no message-level horizontal clipping while code blocks and tables remain scrollable.
4. Commit the implementation and tests.
