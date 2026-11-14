# Progress

## Stage 1 — actual contract audit

2026-11-14: README contains historical claims that conflict with current code. Current widget uses session/chat/preferences/review/confirm/draft-status. Sources inspected: frontend/api.js, widget.js, loader.js, widget-workspace.js; app/api/routes.py and services/conversation_core.py (read only); core-api-contract.md; person3 handoff/install/dependencies/coverage; existing JS tests.

- POST /api/sessions: sessionId, sessionToken, revision, adapterMode; owner header X-Session-Token thereafter.
- GET /api/sessions/{id}: authoritative revision/preferences/history/expiresAt; optional draftState (awaiting/creating/unknown/rejected/completed) and completed draft. No recoverable confirmationToken.
- PATCH preferences with current revision; POST review with revision; POST confirm with exact revision/reviewId/confirmationToken/confirmed. Explicit manual same-body retry only. Server owns idempotency key.
- GET draft-status: draft/opened/mobile_verified/invoiced/paid/active/expired. Cannot recover a missing confirmation token.
- GET local-signup-options?kind=shop|website exists only in local_mock. No production question/options endpoint; existing static question buttons only send their own prompt.
- Session TTL from server expiresAt; review TTL 900 seconds. 404/410 session errors, 409 stale/in-progress, 503 unknown are not interchangeable.

Existing connected forms and exact in-memory retries are already implemented. Main gap: refresh always creates a new session. Planned addition: explicit opt-in tab recovery, minimal owner capability in widget-origin sessionStorage; no history/preferences/confirmationToken persistence. Read server before enabling actions. Unknown/creating locks mutations until GET proves resolution. A lost confirmation token remains a backend/policy dependency.

Tools: PowerShell, Git, Node 24.20.0, Python 3.13.15, installed browser tests using native CDP; subagent available for independent source review. No AGENTS.md. No external/model/production calls planned.

Independent reviewer stage1_review reviewed a supplied source/contract packet (no tools; did not run tests). No definite audit inconsistency; required explicit unknown-state mutation locks and clarified GET cannot resolve unknown or reconstruct confirmation authorization. Accepted all three points; dependencies above do not promise reconciliation. Root ran existing VM session suite: PASS; git diff --check: PASS. Stage 1 complete as an audit; external missing contracts remain dependencies.
