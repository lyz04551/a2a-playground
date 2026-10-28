# Host evidence continuation and final synthesis

## Goal

The Host should coordinate a user goal across specialist Agents. After every specialist result, it should compare the returned evidence with the remaining completion criteria, select a capable Agent for the next missing piece, and continue until the goal is met or progress is no longer possible. The Host then writes the final user answer from all observed work.

## Decision loop

1. `decide_next` receives the original request, live Agent capability catalog, prior decisions, and structured observations. It chooses `delegate`, `clarify`, `complete`, or `stop`.
2. A delegated task declares completion criteria, required tools, and, for a continuation, `continues_task_id`. A continuation may use a different Agent. The referenced task's coverage and tool evidence are passed forward; `depends_on` remains reserved for successful prerequisites.
3. After each Agent result, the Host records a structured evaluation. A partial result or missing required evidence remains insufficient. Coverage checks consider only `coverage_kinds` requested by the user, so discovery metadata does not become an audit target.
4. A `complete` decision is rejected while the latest unresolved specialist result is insufficient. The Host can delegate another focused task or `stop` and explain the partial outcome.
5. On `complete` or `stop`, the Host model synthesizes one final answer using every round's evaluations, limitations, and bounded tool evidence. The prior fixed partial-report template is not used. If the additional synthesis call fails, the already generated Host decision response remains available.

## State and status

The continuation pointer travels with the task evaluation event. Run status treats the earlier insufficient task as superseded by its continuation, including when the next Agent differs. A terminal run remains partial when the latest continuation is insufficient.

## Constraints

- Tool evidence, not Agent prose, supports verified claims.
- The Host may switch Agents only to ones with declared suitable capabilities.
- Existing limits on rounds, tasks, retries, write approval, and post-mutation verification remain in force.
- A stopped run may still contain useful partial Agent reports and a Host summary; it must not be described as fully complete.

## Verification

Tests cover cross-Agent evidence handoff, completion gating, scoped Deployment coverage, final synthesis from all observations, and run status after a cross-Agent continuation. Existing Host orchestration and execution-strategy tests protect approval and event-flow behavior.
