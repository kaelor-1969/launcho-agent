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
| 1 | Both forms/edit/Persian review retained; own-domain loss fixed; six Chrome scenarios pass | Pending |
| 2 | Explicit test catalog23 entries; every preview binding/recommendation; fresh HTTP23/23; missing links unchanged | Pending browser snapshot |
| 3 | Sole trusted handler, synchronous pending lock, native double-click and synthetic rejection checks | Pending final suite |
| 4 | CDP offline, truncated accepted confirmation response, exact identities; no system network changes | Pending final suite |
| 5 | Session-reset form reconciliation added; unknown confirm remains locked/memory-only; expiry/refresh checked | Pending final suite |
| 6 | Late status race fixed; URL allowlist, statuses, handshake/channel gate and loader timeout | Pending final suite / local service |
| 7 | Mobile/desktop/short viewport, accessible names, native keyboard, reduced motion; own-domain Tab added | Pending final Chrome/Edge |
| 8 | Installation/evidence/manifest inspected; original reports are historical until refreshed | Pending final evidence |

No npm build/lint configuration exists. JavaScript syntax, diff checks and applicable actual tests will be used. Backend/public-contract, physical-device, Firefox/Safari and durable-recovery limits remain explicit; no production signup/model/payment test is authorized or claimed.

## Round 2

Not yet complete. No push until final independent review, required tests, evidence and outgoing commit/scope checks pass.
