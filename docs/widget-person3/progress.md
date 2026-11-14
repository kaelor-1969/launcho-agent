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

Stage 4 commit: 145c0d8.

## Resume audit
Readonly Git/docs/code reconciliation found clean branch work/widget-person3-quality at145c0d8; stages1-4 match code. No cause of interruption was recorded in available messages/tool outputs. First unfinished task was stage5. No repeated catalog/network work.

## Stage 5
Safe Persian error/expiry messages; unknown confirmation says do not refresh and labels explicit same-request retry. Pending/resolved flags pass through existing authenticated loader channel (no credentials); host owns beforeunload because sandboxed iframe cannot show dialogs. Chrome1280/390 suite exit0: pending refresh warned and cancellation retained request; resolved refresh made empty memory-only session and never replayed confirm; review/draft/stale expiry invalidated old approval and required manual review. Signup six cases/recovery exit0; VM suite exit0 including missing session freezes replacement operations and adapter unavailable retains unresolved review. Independent reviewer raised adapter certainty: inspection showed availability can change on unknown review, so removed adapter-unavailable from definite-rejection list. Server source confirms stored idem/payload reused; backend effects not tested. beforeunload cannot guarantee mobile/browser termination protection. Durable unknown-result recovery remains blocked by retention/recovery contract.

Stage 5 commit: 02a88cc.

## Stage 6
Added explicit busy status, duplicate GET guard and disabled continuation link after expiry. Current card keeps expired destination disabled; a replacement needs fresh server review. VM hostile URL checks PASS. Chrome session suite final exit0: seven statuses plus unknown, status503/manual retry/one in-flight GET, no confirm side effects, authenticated channel rejects wrong sender/origin/channel/scope, pending refresh still warns, resolved/definite-rejection refresh does not warn. Lazy iframe explicitly installed with data-auto-open=false, no-modals sandbox/title/referrer preserved, handshake hides feedback, blocked iframe times out after15s, reopening retains one iframe and zero API calls. One intermediate Page.navigate timeout has no identified cause; subsequent and final runs passed. A GET fixture record TypeError was fixed. Source-only independent reviewer found no blocker; flags have no session/draft identifier because they are boolean state of the single authenticated iframe.

Stage 6 commit: 29b1ad2.

## Stage 7
No supported-browser matrix found; existing docs name Chrome and exclusions. Chrome157.0.8103.51 and Edge157.0.4341.46 full signup suites exited0: all6 service/viewport scenarios plus recovery. Added native mobile service-modal selection/Escape/focus/value retention, AX visible-control naming (20desktop/16mobile each), reduced motion. No production changes required. browser-coverage.md states Chromium-only/AX-smoke limits, no Firefox/Safari/device/screenreader certification.
Independent stage7 reviewer inspected test source, no own runs; no blocker. Gaps in reverse Tab/focus wrap/Space and dynamic AX states recorded in browser-coverage.md.
