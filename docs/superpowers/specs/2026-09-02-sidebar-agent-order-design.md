# Sidebar Agent Order Design

## Goal

Move the Agents navigation entry above Workspace so users encounter Agent management before starting work.

## Navigation Order

The sidebar order will be:

1. Dashboard
2. Agents
3. Workspace
4. Events

The corresponding Chinese labels remain unchanged: 总览、Agents、工作台、事件.

## Scope

Only reorder the existing sidebar navigation configuration. Do not change routes, icons, labels, styling, permissions, command-palette entries, or page behavior.

## Verification

- Run the relevant frontend tests.
- Build the frontend.
- Confirm the rendered desktop sidebar places Agents immediately above Workspace.
