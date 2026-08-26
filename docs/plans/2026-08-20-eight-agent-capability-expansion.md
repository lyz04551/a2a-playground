# Kubernetes Eight-Agent Capability Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand the playground to eight independently deployable A2A Agents that collectively expose all 66 current Kubernetes MCP tools while keeping Backend healthy and useful with zero, partial, local, or external Agents.

**Architecture:** Each Agent remains a standalone service built on the shared runtime and directly connects to MCP. Tool ownership is declared in Agent YAML, mutating tools use approval, Host routes only through Agent Cards and the dynamic Registry, and Compose offers local Agents without making Backend depend on them.

**Tech Stack:** Python 3.11, Pydantic 2, MCP Python SDK, A2A SDK, FastAPI, pytest/AnyIO, Docker Compose.

---

### Task 1: Tool policy contract and complete catalog coverage

**Files:**
- Create: `tests/runtime/test_agent_tool_coverage.py`
- Modify: `agents/shared-runtime/a2a_runtime/tool_policy.py`
- Modify: `tests/runtime/test_tool_adapter.py`

1. Define the fixed 66-tool MCP contract in a test fixture and the eight Agent configuration paths.
2. Add a failing test proving every server tool is allow/approval in at least one Agent and every exact configured tool exists on the server.
3. Add failing policy tests proving globally blocked drain, cluster registry, Helm uninstall, exec, upload, and file deletion can be explicitly approval-gated by an Agent.
4. Run the focused tests and confirm failures come from current global deny and missing Agent configurations.
5. Reduce permanent global deny so explicit Agent approval rules can own all 66 tools; retain default deny for unmatched tools.
6. Re-run focused policy tests.

### Task 2: Complete the three existing base Agents

**Files:**
- Modify: `agents/k8s-ops/agent.yaml`
- Modify: `agents/k8s-ops/prompt.md`
- Modify: `agents/k8s-security/agent.yaml`
- Modify: `agents/k8s-security/prompt.md`
- Modify: `agents/k8s-orchestrator/agent.yaml`
- Modify: `agents/k8s-orchestrator/prompt.md`
- Test: `tests/runtime/test_agent_tool_coverage.py`

1. Add failing assertions for stable skills, priorities, representative allows/approvals/denies, and removal of `helm_search_repo`.
2. Update Ops with cluster inspection and Pod debug skills; approval-gate exec, upload, file deletion, and Pod deletion.
3. Update Security with explicit security resource queries and representative-object audit workflow.
4. Update Orchestrator with resource management and workload lifecycle skills; approval-gate all resource/deployment mutations and remove nonexistent Helm search.
5. Run coverage and config tests.

### Task 3: Add Infrastructure and Helm base Agents

**Files:**
- Create: `agents/k8s-infrastructure/{main.py,agent.yaml,prompt.md,Dockerfile,requirements.txt,.env.example}`
- Create: `agents/k8s-helm/{main.py,agent.yaml,prompt.md,Dockerfile,requirements.txt,.env.example}`
- Test: `tests/runtime/test_agent_tool_coverage.py`

1. Add failing config/card assertions for IDs, ports 8054/8055, skills, risk levels, and tool policies.
2. Implement Infrastructure with read-only node/storage inspection plus approval-gated node maintenance, default class configuration, and cluster registry tools.
3. Implement Helm with release queries plus approval-gated install/uninstall.
4. Run coverage and config tests.

### Task 4: Add three scenario Agents

**Files:**
- Create: `agents/k8s-incident-responder/{main.py,agent.yaml,prompt.md,Dockerfile,requirements.txt,.env.example}`
- Create: `agents/k8s-capacity-planner/{main.py,agent.yaml,prompt.md,Dockerfile,requirements.txt,.env.example}`
- Create: `agents/k8s-gpu-specialist/{main.py,agent.yaml,prompt.md,Dockerfile,requirements.txt,.env.example}`
- Test: `tests/runtime/test_agent_tool_coverage.py`

1. Add failing assertions for IDs, ports 8056-8058, skills, priorities, risk levels, and representative tool boundaries.
2. Implement Incident Responder with the fixed status/events/logs/resources/network/storage evidence workflow and read-only tools.
3. Implement Capacity Planner with node/pod/top/HPA snapshot analysis and read-only tools.
4. Implement GPU Specialist with template/discovery/diagnostic tools and approval-gated apply/patch/delete/restart/scale.
5. Run coverage and config tests; confirm all 66 tools have ownership.

### Task 5: Decouple Backend and register optional local Agents

**Files:**
- Modify: `docker-compose.yml`
- Modify: `tests/backend/test_backend_import_mode.py`
- Modify or create focused bootstrap tests near: `tests/backend/test_a2a_gateway.py`

1. Add failing tests that Backend startup tolerates an empty Registry and unreachable bootstrap definitions.
2. Verify dynamic registration accepts a standards-compliant external Agent Card without Kubernetes-specific fields.
3. Add five optional Agent services to Compose and expand optional `BOOTSTRAP_AGENTS` to eight local entries.
4. Remove all Agent entries from Backend `depends_on`; keep only independent service configuration.
5. Confirm existing best-effort bootstrap behavior or minimally adjust it so failures never abort startup.
6. Run Backend registration, gateway, import-mode, and Host decision tests.

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `guide.md`
- Modify: `DESIGN.md`

1. Document the eight-Agent topology, ports, tool domains, optional startup, and external A2A integration.
2. Run `pytest -q tests/runtime`.
3. Run focused Backend tests and then `pytest -q` if focused tests are green.
4. Run `npm --prefix frontend test` and `npm --prefix frontend run build`.
5. Run `python -m compileall -q agents backend` and `docker compose config`.
6. Run `git diff --check`, inspect only feature-related diffs, and report unrelated pre-existing failures separately.

### Working-tree constraint

The current checkout contains substantial user-owned modifications in files this feature must also touch. Preserve all existing content, use narrow patches, do not reset or discard changes, and do not create intermediate commits that could accidentally include unrelated work. The already committed design document remains separate.
