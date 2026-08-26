# MCP Dual HTTP Transport Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow all shared-runtime Kubernetes Agents to select either Streamable HTTP or legacy HTTP+SSE MCP transport through `MCP_TRANSPORT`.

**Architecture:** Validate the transport in `AgentRuntimeConfig`, pass it into `K8sMCPClient`, and isolate SDK-specific context-manager shapes behind the client's connection method. Keep `sse` as the default and do not auto-detect or fall back.

**Tech Stack:** Python 3.11+, Pydantic 2, MCP Python SDK, pytest/AnyIO.

---

### Task 1: Configuration contract

**Files:**
- Modify: `tests/runtime/test_config.py`
- Modify: `agents/shared-runtime/a2a_runtime/config.py`

1. Add tests proving omitted transport defaults to `sse`, both supported values load, and an unsupported value raises `ValidationError`.
2. Run the focused tests and verify the new assertions fail because the field does not exist.
3. Add a typed `mcp_transport` field accepting only `sse` and `streamable_http`, populated from `${MCP_TRANSPORT:-sse}` in all Agent YAML files.
4. Run the focused tests and verify they pass.

### Task 2: Transport selection

**Files:**
- Modify: `tests/runtime/test_mcp_client.py`
- Modify: `agents/shared-runtime/a2a_runtime/mcp_client.py`
- Modify: `agents/shared-runtime/a2a_runtime/agent.py`

1. Add tests exercising observable session initialization through the SSE and Streamable HTTP context-manager shapes.
2. Run the focused tests and verify Streamable HTTP selection fails.
3. Add explicit transport selection, handling the Streamable HTTP client's third session-id callback return value.
4. Pass the validated config from `RuntimeMCPAgent` into the shared client.
5. Run MCP client and runtime tests and verify they pass.

### Task 3: Deployment configuration and documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `agents/k8s-ops/.env.example`
- Modify: `agents/k8s-orchestrator/.env.example`
- Modify: `agents/k8s-security/.env.example`
- Modify: `README.md`
- Modify: `guide.md`

1. Add `MCP_TRANSPORT` to all three Compose Agent environments and `.env.example` files.
2. Document valid URL/transport pairs and the backwards-compatible default.
3. Check the diff for accidental changes outside the feature scope.

### Task 4: Verification

1. Run `pytest -q tests/runtime/test_config.py tests/runtime/test_mcp_client.py`.
2. Run the complete runtime test directory.
3. Run formatting/diff checks and report any unrelated pre-existing failures separately.
