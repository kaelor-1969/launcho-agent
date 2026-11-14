# Progress

## Initial inspection
- Existing forms/review/editing landed in `3e68204`; avoid rebuilding them.
- Node v24.20.0, Python 3.13.15; native Chrome/CDP browser tests need no npm install.
- Commands: `node --experimental-vm-modules tests/widget_session_test.cjs`, `node tests/widget_signup_browser.cjs`.
- Contract: docs/core-api-contract.md and frontend/api.js. Chat retry keeps requestId; confirmation retry keeps revision/reviewId/confirmationToken; idempotency belongs to server. Tokens stay in iframe memory.
- No reliable cumulative chat token counter or root-session transfer tool available. The exact 200,000-token threshold cannot be enforced. Keep handoff current.

## Stage 1
Existing implementation retained. VM and Chrome signup suites passed (six service/viewport combinations and recovery). Independent source-excerpt review approved; reviewer did not execute tests. No frontend change needed. Production options remain blocked. Commit: see stage-1 commit in git log.

Stage 1 commit: a72b5ea.

## Stage 2
23 shop fixture templates match the 23 public visible rows with links. Public evidence has 26 rows: 25 visible, 1 hidden; khodro and danesh have no link. Website has one local sample, no preview. All 23 HTTP URLs reachable; all 23 Chrome rendering smoke checks passed. Full signup suite with every preview binding and every category recommendation passed. Source-only independent review approved. HTTP/rendering does not verify full asset loading, visual equivalence or registration availability. Reports: catalog-audit.json, public-preview-browser.json.

Stage 2 commit: ce48fd7.

## Stage 3
Chrome session suite PASS at1280/390: real pointer double-click plus extra Enter create only one in-flight request; exact review body retained. Synthetic activation rejected. Reviewer found a test race in immediate server-call counting; fixed by atomically asserting synthetic click never disables confirm. Rerun exit0; second review approved. No production change needed.

Stage 3 commit: 3c0e015.

## Stage 4
Chrome session suite exit0 at1280/390 with CDP offline transport (no system network changes). Offline chat never reached HTTP fixture; reconnection alone did not resend in100ms observation; manual retry matched captured original postData and one user bubble. Confirm fixture flushed partial JSON then destroyed socket after recording accepted body; UI froze edits and manually retried identical confirmation. Source reviewer approved, no own execution. Fixture does not prove backend operation deduplication.
