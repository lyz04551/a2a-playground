# Run quality and evidence design

## Goal

Make Auto runs honest about completion and auditable from the workspace. A run may finish fully, finish with a documented coverage gap, or stop because required evidence is unavailable. A successful transport or Agent response alone must not imply full task completion.

## Contract

For finite multi-target tasks, the Host declares that coverage is required. A specialist may return a domain-neutral coverage manifest with a scope, expected targets, inspected targets, enumeration completeness, and observed tool-call IDs. The runtime rejects references to unknown call IDs. If enumeration cannot be evidenced, coverage stays unknown rather than inferred from the request text or tool names. Evidence entries contain tool name, target, call ID, invocation time, outcome, and a bounded result excerpt. Findings refer to evidence IDs. Empty logs distinguish `empty` from `not_requested` and `failed`.

The Host compares coverage and evidence to completion criteria before deciding. An incomplete read-only assessment can be useful, but its terminal run state is `partial`, not `completed`. Contradictory or unsupported findings trigger one focused correction; if still unresolved, the run stops with `evidence_insufficient`. The user sees the covered and missing targets at the top of the final answer.

## Execution

For broad audits the Host first enumerates targets, partitions them into batches that fit the Agent tool budget, and checkpoints the manifest. Continuations receive only remaining targets and existing evidence references. Per-run caps limit rounds, calls, and time. The Host may stop with partial results once the cap is reached.

## UX

The workspace uses distinct terminal badges: 完全完成, 部分完成, 证据不足而终止. A compact coverage bar and expandable evidence cards sit beside the final report. Draft Agent messages remain visibly unverified until the Host accepts them. Agent capabilities and risk labels come from the active runtime policy, and drift is shown as a health issue.

## Verification

Regression scenarios cover a completed audit, incomplete Deployment enumeration, empty versus missing logs, contradictory termination reason, high-restart Running Pods, budget continuation without rescanning, and Agent Card policy drift. All cluster tests are read-only; mutation approval is checked with fixtures.
