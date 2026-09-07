# Logical Mutation Continuation Design

## Problem

The Host currently treats a successful approved MCP write as proof that the
whole delegated mutation task is complete. That is incorrect for compound
goals. A task such as "delete the broken Pod and recreate it with a corrected
image" can execute only the delete, be marked sufficient, and move directly to
verification. The verification then correctly reports that the Pod is absent,
but the correction limit prevents the missing create from continuing. The Run
can finally be labelled completed even though the user's goal was not met.

The fix must remain generic. The Host coordinates specialist Agents through
A2A, while the Agents choose and invoke MCP tools. The Host must not hard-code
Kubernetes tool sequences, and the MCP protocol and approval semantics must not
change.

## Goals

- Evaluate completion against the complete delegated task, not a single MCP
  call.
- Resume the same logical mutation task after every approved tool call until
  its completion criteria are met or it becomes blocked.
- Keep every concrete write tool call independently approved.
- Count correction allowance by logical mutation task, not by tool call or
  approval.
- Route all Kubernetes writes to K8s Resource Orchestrator Agent and keep K8s
  Ops Agent read-only.
- Prevent a Run from becoming completed when its requested terminal outcome is
  unmet.

## Non-goals

- No MCP request, response, digest, or approval protocol changes.
- No hard-coded `delete` followed by `apply` rule in the Host.
- No automatic approval of a second write because a first write was approved.
- No general workflow language or arbitrary DAG interpreter.

## Responsibilities

### Host Agent

The Host owns the logical task, its stable identity, completion criteria,
workflow role, and lifecycle. It decides whether a completed Agent response is
sufficient, incomplete, blocked, or failed. A continuation of an incomplete
logical task does not create a new correction.

### K8s Security Agent

The Security Agent performs read-only prechecks and returns structured evidence
and a continuation recommendation. It does not execute mutations.

### K8s Resource Orchestrator Agent

The Resource Orchestrator owns Kubernetes create, apply, patch, delete, and
replace operations. It may invoke more than one write MCP tool to satisfy one
logical task. Each write independently passes through ToolPolicy and Human
Checkpoint.

### K8s Ops Agent

The Ops Agent diagnoses and verifies using read-only tools: resource state,
events, logs, and metrics. It may recommend a correction but must not execute
delete, apply, patch, or other mutations.

## State and data model

The existing `PlannedTask` remains the source of the logical task definition:

- `id`: stable logical task ID across approval resumptions and incomplete
  continuations;
- `workflow_role`: `precheck`, `mutation`, or `verification`;
- `objective`, `input`, and `completion_criteria`: the complete desired result;
- assigned Agent capability and risk.

No Kubernetes-specific tool sequence is added to the Host model. Instead, the
persisted observation must distinguish execution transport success from task
goal completion:

- `result.state=completed`: the Agent/A2A turn ended normally;
- `evaluation.outcome=sufficient`: the complete task criteria were met;
- `evaluation.outcome=insufficient`: the turn completed but the same logical
  task still has work remaining;
- `evaluation.outcome=blocked|failed`: continuation is unsafe or impossible.

Approval resume must never manufacture a `sufficient` evaluation merely because
one approved MCP call returned successfully.

## Execution flow

1. Host delegates a mutation task with a stable logical ID and explicit final
   completion criteria.
2. Resource Orchestrator invokes a write MCP tool.
3. ToolPolicy emits a pending action; the Run pauses at Human Checkpoint.
4. After approval, the backend resumes the same remote A2A task and persists the
   tool result.
5. If the Agent emits another pending action, the backend exposes another Human
   Checkpoint under the same logical task. No task completion or Host summary is
   emitted between approvals.
6. When the Agent turn completes, the Host evaluator checks the entire original
   completion criteria against the accumulated result and tool evidence.
7. If sufficient, the mutation task completes and the Host may schedule a
   separate Ops verification round.
8. If insufficient, the same logical task remains active and is continued with
   the missing criteria and prior evidence. This continuation does not consume
   another corrective mutation allowance.
9. If blocked or failed, the Host stops or asks for necessary user input. It
   must not report the Run as successfully completed.

For a delete-only objective, successful deletion satisfies criteria such as
"the target resource is absent", so the task completes after one approval. For
a replace objective, deletion alone cannot satisfy criteria such as "the
corrected resource exists", so the same task continues until recreation is
approved and completed.

## Deterministic guardrails

- `workflow_role=mutation` may only target an Agent advertising the resource
  mutation capability. In the current three-Agent deployment this is K8s
  Resource Orchestrator.
- K8s Ops configuration must expose only read tools. This prevents an erroneous
  Host choice or Agent response from bypassing role separation.
- The correction limit counts distinct successful logical mutation tasks in
  Host state. Approval count, tool-call count, and continuation count do not
  affect it.
- Verification remains a later round and requires a sufficient mutation
  observation.
- Host `complete` requires the final verification required by the user goal to
  be sufficient. A `stop` caused by unmet criteria maps to a non-success
  terminal state such as blocked, rather than `run.completed`.

## Failure handling

- Rejected approval blocks the current logical task and records the exact
  rejected action; it is not silently retried.
- A successful intermediate write followed by Agent transport failure leaves
  the task incomplete with its completed tool evidence preserved. The Host can
  continue the same logical task without repeating the completed write.
- If the Agent claims completion without satisfying its criteria, evaluation is
  `insufficient`; the continuation prompt states the unmet criteria and already
  completed actions.
- Repeated insufficient responses are bounded by the existing task-attempt and
  Host-round limits. Exhaustion produces a blocked/failed Run with a truthful
  summary.

## User-visible behavior

- Every write displays its own approval card below the same delegated task.
- Intermediate approvals update tool activity but do not create a fake Host
  summary or a completed task badge.
- A compound repair shows delete completed, then create awaiting approval, then
  task completed only after both are done.
- Final verification and Host summary state the actual terminal resource state.

## Testing

Backend regression coverage must include:

1. delete-only mutation completes after its approved delete;
2. replace mutation remains incomplete after delete and requests/continues the
   create under the same logical task;
3. each write receives a distinct approval ID and digest;
4. multiple approvals do not consume multiple correction slots;
5. mutation tasks cannot route to K8s Ops;
6. K8s Ops cannot invoke write tools;
7. verification cannot start after an insufficient mutation;
8. unmet terminal criteria cannot produce `run.completed`;
9. replay/reconnect reconstructs the same logical task and all approval/tool
   states.

Frontend regression coverage must confirm that sequential approval cards remain
grouped beneath the corresponding task and that intermediate tool completion
does not mark the task or Run complete.
