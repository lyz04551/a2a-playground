# Backend Run Stability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize durable Run event queries, add compatible pagination, replace SSE busy polling, and recover interrupted Runs after restart.

**Architecture:** Add backward-compatible SQLite columns and indexes, opt-in pagination helpers, an in-process Run notification primitive backed by durable replay, and conservative startup recovery.

**Tech Stack:** FastAPI, asyncio, SQLAlchemy 2, SQLite, Pydantic 2, React API client.

---

1. Add event columns, automatic migration/backfill, and query indexes.
2. Add repository pagination and opt-in API pagination for conversations, events, and Runs.
3. Add Run event notifications and replace 100ms reconnect polling with notification waits.
4. Add conservative restart recovery and invoke it during application startup.
5. Run full backend/frontend regression, build, compile, schema inspection, and diff checks.
