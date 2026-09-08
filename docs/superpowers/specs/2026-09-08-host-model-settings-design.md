# Host Model Settings Design

## Scope

Add a **Model Settings** page below **Events** in the main navigation. It displays and updates only the Host Agent model configuration. Child Agent model configuration and running Runs are unchanged.

## Configuration model

- Fields: provider, base URL, model name, API key.
- Environment variables remain the deployment defaults.
- A persisted runtime override, when present, takes precedence for newly created Host Runs.
- Saving an empty API key keeps the existing key. The backend never returns the key; it returns only `api_key_configured`.
- Clearing the runtime override restores environment defaults.
- Existing/running Runs retain the configuration with which they started.

## Backend

- Persist a singleton Host model override in PostgreSQL through a migration and repository methods.
- Add authenticated console endpoints:
  - `POST /api/model-config/get`
  - `POST /api/model-config/update`
  - `POST /api/model-config/reset`
- Validate provider, URL, and model before saving.
- Store the API key encrypted using a deployment encryption key. If that key is not configured, model metadata remains editable but API-key replacement is rejected with a clear error.
- Host manager creation resolves the effective configuration from database override first and environment defaults second.

## Frontend

- Add `/model-settings` and a navigation entry immediately below Events.
- Show effective provider, base URL, model, source, and API-key configured state.
- Provide Save and Restore Environment Defaults actions with loading, success, validation, and error states.
- The API-key input is always blank and uses password masking.

## Verification

- Backend tests cover secret redaction, validation, persistence precedence, reset, and new-Run application.
- Frontend tests cover navigation, form payload behavior, and API-key retention semantics.
- Run the relevant backend tests, full frontend test suite, and production frontend build.
