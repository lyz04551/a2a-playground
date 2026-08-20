# Run Feedback and Operation Safety Design

## Goal

Make active execution state unmistakable and ensure approval/tool details remain
useful without exposing sensitive values.

## Scope

This phase adds five related behaviors:

1. A stop action remains available for every non-terminal Run, including restored
   Runs that are no longer attached to the original browser stream.
2. The workspace distinguishes connecting, connected, reconnecting, recovered,
   interrupted, and idle connection states.
3. Approval cards show risk, action identity, arguments, and a field-level comparison
   with the previous approval for the same Run, Agent, and tool when available.
4. Tool details recursively redact sensitive fields before rendering, copying, or
   downloading. Results remain collapsible.
5. Status changes are announced through an unobtrusive `aria-live` region.

Agent health history, conversation favorites/search, and comprehensive drawer focus
management are deferred to the next UX phases.

## Interaction design

The workspace keeps its compact operations-console style. Connection feedback appears
as a narrow status strip above the message timeline. Reconnecting uses the existing
warning treatment; recovery uses a brief success treatment and then settles to the
connected state. Errors remain persistent.

The composer stop button remains while a local request is active. A second stop action
in the Run trace header is visible whenever the durable Run status is non-terminal,
so restored executions can also be cancelled.

Approval cards use risk tags (`read`, `write`, `critical`) and a structured diff with
added, removed, and changed fields. The comparison is informational; the backend action
digest remains the authorization boundary.

Tool detail actions operate only on a recursively redacted object. Sensitive key names
include password, secret, token, authorization, cookie, API key, private key, and
credential variants. Redaction applies at any nesting depth and inside arrays.

## Data flow

`streamRun` emits connection lifecycle callbacks. `useRunStream` maps them into a small
connection-state object and exposes durable `canCancel`. Approval comparison is derived
from approvals already returned by the Run detail endpoint, so no schema migration is
required. Tool redaction and serialization are pure frontend utilities.

## Verification

Final regression covers the existing frontend and backend suites, the production build,
API route uniqueness, Python compilation, and diff whitespace. Focused utility tests are
added only for recursive redaction and approval diff because those rules protect data and
are otherwise difficult to validate through current component tests.
