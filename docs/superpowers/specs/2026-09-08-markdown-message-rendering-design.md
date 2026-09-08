# Markdown Message Rendering Design

## Scope

Render Agent and Host response bodies as readable Markdown in the workspace and Run Trace. User messages, tool arguments/results, approvals, raw events, and debug JSON remain plain text.

## Rendering

- Use `react-markdown` with `remark-gfm` for headings, emphasis, lists, blockquotes, links, fenced code, and tables.
- Normalize common transport escaping only when Markdown punctuation is escaped (`\#`, `\*`, `\|`, `\_`, and similar).
- Do not enable raw HTML rendering.
- Open links safely in a new tab.

## Layout

- Keep typography compact inside message cards.
- Put tables and code blocks in bounded internal scroll containers.
- Prevent content from widening the workspace.
- Apply the shared renderer to workspace Agent/Host messages and Run Trace Agent/Host result text.

## Verification

- Unit-test escape normalization and renderer wiring.
- Run the frontend test suite and production build.
