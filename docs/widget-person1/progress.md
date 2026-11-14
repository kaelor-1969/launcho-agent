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

## Stage 2 — opt-in tab recovery

Stage 1 commit: 8d7b272. Added data-session-recovery="tab" (default remains memory). Only session owner ID/token plus unresolved flag retained in widget-origin sessionStorage, partitioned by embedding origin; no messages/preferences/confirmation token. GET restores authoritative revision/history/preferences. Unknown/creating and interrupted pending requests lock all mutation handlers and expose explicit GET retry. Pending session expiry does not create replacement. Completed recovery checks draft-status before exposing validated continuation; expired link disabled. New module/document cache versions applied.

Root actual tests: existing session VM PASS; new recovery VM PASS (scope, pending marker before POST, terminal clearing, expiry, malformed/blocked storage, invalid server state); new native Chrome recovery browser PASS (host/iframe reload, form/history restore, unknown/creating locks, pending expiry, completed/status/expired, zero confirm calls). Generated evidence: artifacts/widget-person1/recovery. git diff --check PASS.

Fresh reviewer stage2_review had no tools and reviewed behavior/source packet only, did not execute tests. No definite bug identified; requested interrupted-send, terminal marker, overlap, status failure, storage-write and mutation prohibition checks. Root added interrupted-awaiting VM case, validates draft-status enum and guards typing from hiding recovery guidance. UI sessionStarting serializes recovery attempts; malformed status cannot expose restored links. Further browser failures/reconnect coverage in stage 3. Unknown-operation forced-refresh retry remains dependent, not complete.

## Stage 3 — offline and duplicate prevention

Stage 2 commit a01667a. Added an accessible offline notice in both interfaces. Online/offline listeners only render text; they never call transport. Expanded recovery browser checks for malformed status, real CDP offline GET, reconnect without requests and explicit manual read retry. Root existing sessions browser checks exact chat requestId and confirmation bodies after accepted response loss, native double activation, loader and timeout. Updated its unknown-status expectation to the transport's safe rejection message, retaining the same scenario and request-count assertions.

Root recovery browser and existing session VM PASS. Existing Chrome sessions suite at1280/390 PASS (including lazy iframe, authenticated pending flags, status/error retry, expired link and loader timeout). Fresh reviewer stage3_review source-packet review: no blocker; did not run tests. Suggested offline-at-load, pending reconnect, repeated transitions and both-interface parity remain additional coverage opportunities; current offline checks are workspace Chromium, not physical devices. git diff --check PASS. No guarantee of exactly-once backend execution.
