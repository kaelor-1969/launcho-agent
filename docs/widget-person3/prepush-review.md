# Two-round review before branch publication

## Branch isolation

- Original delivery preserved: `work/widget-person3-quality` at `bf1a622`.
- Fresh publication branch: `work/widget-person3-reviewed`, based on fetched `origin/main` = `96cc945883b80487afe1cefadc7731cd29ef4435`.
- Original local `main` had unpublished `3e68204` (widget UI prerequisite) and `6ff86df` (Python asset-cache changes). The new branch carries only the reviewed frontend/JS prerequisite as `050b975`; no Python/cache commit or documentation outside this task was imported.
- The eight task commits were replayed without changing the original branch: `fcece8c`, `1e377fe`, `bfd5639`, `5bc94b2`, `23b2117`, `cb7128a`, `0839f4a`, `d5d7b8b`.
- No AGENTS.md found in repository/ancestor paths. Original pasted instructions reread. Remote has no existing `work/widget-person3-reviewed` branch at isolation time.

## Round 1 — implementation and requirements

Independent reviewer had no tools; supplied exact API/form/review/confirmation/status/loader logic, contracts, acceptance and coverage. No independent execution attributed to reviewer.

Findings and fixes:
1. Existing-domain loss: review supported `ownDomain`, edit/save did not. Both widget variants now display/validate/round-trip existing domains; new-domain fields are disabled while one is supplied. Invalid existing domains produce no request. Native keyboard test includes the new field.
2. Session replacement left stale form choices: transport now returns its own `sessionRestarted` flag; UI resets the form/catalog selection and applies the new response preferences, invalidates the old review and explains the new session. Expired-session retry retains message requestId, changes session ID explicitly and never confirms.
3. Late status response could overwrite a fresh review: the callback verifies that its captured link still owns the visible review before updating notices. Late success/error for a detached/hidden card is ignored.
4. Remote catalog separation: general mock now intentionally contains no approved options; controlled tests and public audits read the explicit test-only widget catalog, matching the local gateway. No catalog data changed. Empty/unavailable catalog is tested as disabled.
5. Public audit previously exited successfully even for unreachable results; it now fails for HTTP/network/foreign-origin redirect failures. Browser preview smoke also checks that the requested template label is visible.

Actual round-1 checks: Chrome form suite exit0 (six scenarios plus new own-domain/empty-catalog/session-reset cases); VM session suite exit0 including late-status race; Chrome session/loader suite exit0 including a delayed status racing a newer review. Fresh HTTP audit 23/23 reachable, exit0. Public browser refresh running at this checkpoint.

| Stage | Round-1 implementation evidence | Round-2 validation |
| --- | --- | --- |
| 1 | Both forms/edit/Persian review retained; own-domain loss fixed | PASS Chrome+Edge six cases, existing-domain round-trip; actual local FastAPI/mock both kinds1280/390 |
| 2 | Explicit test catalog23 entries; every preview binding/recommendation; missing links unchanged | PASS freshHTTP23/23 and publicChrome23/23 with expected template label visible; not official registration evidence |
| 3 | Sole trusted handler, synchronous pending lock | PASS native double-click/extra Enter/synthetic rejection in Chrome+Edge |
| 4 | CDP offline, truncated accepted confirmation response, exact identities | PASS Chrome+Edge, same requestId/review body, no system network changes |
| 5 | Session reconciliation; unknown locked/memory-only; expiry/refresh | PASS including creation503 and first-new-reply503 followed by manual retry; no replacement confirmation; forced-refresh recovery remains external |
| 6 | Late status race fixed; URL allowlist, status/handshake/channel and timeout | PASS Chrome+Edge delayed status/new review, full status cases and loader; actual two-origin service forms/review pass |
| 7 | Mobile/desktop/short viewport, native keyboard, reduced motion | PASS Chrome+Edge,21desktop/17mobile named AX controls; documented screenreader/device/Safari/Firefox limits remain |
| 8 | Installation, source hashes, selected images and four safe reports | PASS final evidence refreshed; exact hashes/membership and outgoing scope verified before push |

No npm build/lint configuration exists. JavaScript syntax, diff checks and applicable actual tests will be used. Backend/public-contract, physical-device, Firefox/Safari and durable-recovery limits remain explicit; no production signup/model/payment test is authorized or claimed.

## Round 2

Fresh independent reviewer received the final logic, new scenarios and actual results; no file/test tool access and no independent execution claimed. No remaining blocker found. The reviewer required final reruns and exact final evidence/scope; these gates are applied before publication.

Additional round-2 correction: a per-call restart flag was insufficient if creating the replacement session or its first chat reply failed. The API now keeps `needsReconciliation` from before replacement creation until a validated chat response reaches UI. Both failure/retry paths were added to the real Chrome/Edge form suite and passed on rerun.

Actual validation:
- Full `node tests/widget_quality_check.cjs` exit0 in Chrome157.0.8103.51 and Edge157.0.4341.46; affected signup suites repeated after the last restart correction, exit0 in each browser.
- Fresh read-only HTTP23/23 and browser23/23 public previews, exit0. Preview test requires requested label plus URL/text/loaded image; full asset loading/visual equivalence/official availability remain unverified.
- Actual local FastAPI + mock, ports8040/8041 (different origins), temporary isolated databases: `WIDGET_REVIEW_ONLY=1 node tests/widget_live_workspace_browser.cjs` exit0 for both kinds at1280/390, own domain retained, zero chat/confirm requests. This is local backend integration, not production Launcho. Added test-only lexical variable declaration initially failed; wrapped in IIFE and rerun passed.
- Existing Python suite: default Windows encoding failed; parent-only `-X utf8` left one child-process failure. Inherited `PYTHONUTF8=1` produced **162 tests OK**, exit0. No Python source modified.
- All frontend JS and widget CJS syntax and diff checks passed. No npm lint/build task exists; no frontend build step was invented. Docker backend deployment was not run or claimed.

Evidence uses final rerun reports/screenshots, with implementation source hashes in evidence-manifest.json to identify the exact tested code independently of documentation commit SHA. No tokens, database, env file or transient log is committed. Old branch and all user commits preserved. User explicitly authorized dedicated-branch push after these gates, not PR/main/force/merge/deploy.

Final round2 reviewer verdict: PASS for implementation candidate341b0985feced3370bfd5c709e65d9f9f84a9385 after final Chrome/Edge reruns,162Python tests, fresh23previews and exact evidence/source-hash checks. Documentation-only publication wording follow-up does not change tested code. Both reviewers disclosed no tools/own executions. Final remote destination, outgoing commits, local cleanliness and Git-blob evidence/source hashes are checked immediately before the authorized branch-only push; exact final SHA is verified against the remote and reported in chat.
