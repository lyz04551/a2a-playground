# K8s Resource Orchestrator Rename Design

## Goal

Clarify that the existing Orchestrator Agent orchestrates Kubernetes resources through MCP, while the Host remains responsible for A2A multi-Agent orchestration.

## Naming

- Change the public Agent name from `K8s Orchestrator Agent` to `K8s Resource Orchestrator Agent`.
- Use the Chinese description `K8s 资源编排 Agent` in Chinese documentation.
- Keep `k8s-orchestrator` as the stable Agent ID, directory name, Compose service name, URL hostname, and approval identity.

Keeping the internal identifier avoids breaking persisted Agent registrations, approval continuations, Compose networking, tests, and external clients that already reference `k8s-orchestrator`.

## Responsibility Boundary

The Host is the only system-level A2A coordinator. It discovers Agents, routes and decomposes tasks, controls cross-Agent execution order, and aggregates results.

The K8s Resource Orchestrator is a specialist A2A server. It uses MCP tools to create, apply, patch, scale, restart, delete, and verify Kubernetes resources. It does not discover, invoke, or coordinate other Agents.

## Changes

- Update the Agent Card name, description, skills, examples, limitations, and prompt to emphasize Kubernetes resource lifecycle management.
- Update current user-facing documentation and active tests that assert the public name.
- Preserve historical design documents and plans as records of their original decisions unless they describe current runtime behavior.
- Do not rename source directories, Docker Compose services, ports, environment variables, or stable Agent IDs.

## Verification

- Agent configuration tests confirm the new public name and unchanged `k8s-orchestrator` ID.
- Tool-policy tests continue to confirm that mutations require approval.
- Backend and Compose tests confirm the existing stable ID still registers and routes correctly.
- The full Python and frontend test suites remain green.
