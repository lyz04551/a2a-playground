# Host Three-Way Decision Design

## Goal

Let the Host model decide whether to answer, clarify, or delegate without keyword
classification or mandatory child-Agent work.

## Contract

`HostPlan` gains an `action` discriminator with three values:

- `direct_response`: answer from Host knowledge; `response` is required and tasks are empty.
- `clarification`: ask the user for missing information; `response` is required and tasks are empty.
- `delegate`: use one to six tasks; `response` is empty and work flows through A2A.

Pydantic cross-field validation rejects mixed or incomplete decisions. Existing tests and
fixtures that omit `action` remain compatible by defaulting to `delegate`.

## Model decision

The planning prompt describes behavioral boundaries but contains no keywords, regexes,
or deterministic intent classifier. The model evaluates whether registered Agent
capability or external execution is actually required. It must clarify before delegation
when essential scope or target information is missing.

## Execution

All decisions emit `plan_created`. For direct/clarification plans the engine emits the
Host response and `done` immediately; it never invokes evaluation, synthesis, or the A2A
delegate. Delegated plans retain the existing orchestration path unchanged.

The normalized Run layer persists the same message and terminal events, so existing
frontend reducers and trace components continue to work without special-case routing.
