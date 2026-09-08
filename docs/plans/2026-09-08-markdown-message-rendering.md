# Markdown Message Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Render Agent and Host reports as safe, responsive Markdown.

**Architecture:** A shared normalizer and React renderer form one boundary for model-authored content. Workspace messages and Run Trace outputs consume it while raw operational payloads remain unchanged.

**Tech Stack:** React, react-markdown, remark-gfm, CSS, Node test runner.

---

### Task 1: Shared Markdown renderer

Add dependencies, normalization tests, `MarkdownContent`, and bounded responsive styles.

### Task 2: Integrate message surfaces

Use the renderer in Agent/Host workspace messages and Run Trace Agent/Host output without changing user or tool payload rendering.

### Task 3: Verify and publish

Run frontend tests, production build, `git diff --check`, commit, and push to `main`.
