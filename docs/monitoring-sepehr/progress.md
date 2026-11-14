# Progress

## Stage 1

Read README, existing operations documentation, health routes, loader handshake,
widget initialization, existing monitor/tests and Git history. Historical claims
were checked against current code; no historical environment is treated as live.
Python venv, Playwright and installed Chrome 157 work. Node 24 is also available.
Initial Git tree clean; no existing monitoring branch. No secrets read or printed.
Primary review: no product/database/deployment changes required for baseline.
Validation: Chrome launched and closed successfully through Playwright.
Independent reviewer received code excerpts because its tools were unavailable;
no independent execution claimed. No material baseline defect; reviewer reinforced
the documented distinction between configured UI shell and session readiness.

Stage-1 commit: `e28d95c`.

## Stage 2

Added independent availability HTTP probes and explicitly local example config.
Total asyncio deadline, 16 KiB decoded-byte limit, no proxy environment, redirect
rejection and exact JSON status contracts. Serial loop sleeps after completion.
Primary review: no application imports, DB writes, secret URLs or response bodies.
Independent evidence-only review suggested bool rejection, timeout exception order,
decoded bytes and media-type parameters; all four are already implemented.
Validation: four unit tests with controlled local HTTP servers. First run exposed
Windows loopback refusal taking longer than the one-second test deadline; adjusted
the refusal case to five seconds, preserving the separate 100ms timeout test.

Stage-2 commit: `aacc6e6`.

## Stage 3

Real Chrome on separate host/widget origins serving actual frontend assets.
No frontend/product changes. Existing configured visibility, editable textarea and
working close button establish shell readiness. Every non-GET/HEAD is blocked
before navigation, workers blocked, sockets closed; no session is fabricated.
Six scenarios passed: healthy, loader 503, iframe 503, missing handshake, module
exception, optional images 404. Receiver observed zero writes in every scenario.
Healthy/optional scenarios observed blocked session initialization, explicitly
`session_verified: false`. Failure screenshot is optional and fully masked;
safe diagnostics retain stage/counters only, no URLs/errors/page text.
Browser launch itself now uses the configured deadline as well as page probing.
Raw local evidence is ignored under `artifacts/monitoring/browser-results.json`.
Independent evidence-only reviewer requested actual loaded-frame URL validation;
added before interaction. Also blocked GET `/api/` requests. Stack attribution
uses the current repository's `/widget/` module layout; future relocated scripts
require review. Deadline covers all interactions; cleanup runs in finally. Origin
filtering is not a guarantee that an arbitrary host's GET handlers are side-effect
free: only approved hosts with safe resource GETs may be monitored.

Stage-3 commit: `81a1865`.

## Stage 4

Separate live/ready/widget incident states, default three failures to open/two
successes to recover. Atomic JSON state tied to target identity; exclusive lock
prevents concurrent monitor instances using the same state. Restart preserves
streaks/incidents. No reminders, cooldown retransmits or replay. Persist-before-send
can lose notifications in a crash gap; delivery is a bounded send sequence, not
exactly-once transport. Corrupt/mismatched state fails closed without overwriting.
Four incident tests passed, using controlled outcomes without long clock waits:
transient/persistent/recovery with restart after each sample; corruption/target
change; widget-only incident with failed delivery and no replay; lock exclusion.
Independent evidence-only review confirmed lock acquisition is outside the owned
lock cleanup try/finally. Added a fifth test for os.replace failure: no alert is
sent when persistence fails. Persistence failure stops monitoring visibly instead
of risking an alert storm; operator must repair the monitor state volume.

Stage-4 commit: `4709878`.

## Stage 5

Generic environment-only webhook transport, default dry-run, optional Bearer token,
HTTPS except loopback, strict header validation, no redirect/proxy environment,
bounded attempts/deadlines and no credential-bearing logs. One labelled test mode.
Initial four local receiver tests passed; added timeout/refused-connection test
after independent evidence-only reviewer noted that gap. No actual channel chosen
or tested; user expressly requested the synthetic receiver. Same event ID must be
deduplicated by receivers if a response is lost between attempts. Failed send
sequences are not replayed: notification may be lost permanently.

User supplied development host launchox.ir and service ag.launchox.ir. A real
read-only one-shot run passed both health contracts and browser loader/frame/shell
on those hosts, blocked one automatic session POST, observed one optional-resource
failure and no essential/JS failure. Session was not verified. Browser security
was unchanged. Web text-fetch tool could not access these URLs, but actual local
HTTP/Chrome monitor execution succeeded. launcho.ir remains final acceptance only.

Stage-5 commit: `7a6c0d7`.

## Stage 6

Owned real FastAPI and local mock API subprocesses with isolated temporary databases,
blank AI credentials/invalid AI destination and a separate local host/alert receiver.
Initial full drill passed all 15 observation/assertion groups, including restart
after every sample, exact payload/count checks and cleanup of every owned resource.
Independent reviewer suggested stronger startup ownership; added own Uvicorn log
marker plus process liveness and HTTP readiness. A simultaneous validation run
exceeded the original 10-second cold-start budget; a 30-second startup budget
repeat then passed. No check was skipped or weakened; health/UI acceptance unchanged.

Primary/fresh independent source-excerpt reviews also found and fixed:

- HTTPX default 5-second deadline could override a longer configured total timeout.
  Both health/sender clients now use timeout=None inside the outer total deadline.
  Real 5.1-second controlled response with configured 7-second budget tests this.
- JSON parser RecursionError now yields invalid_json without stopping the monitor.
  Python 3.13 accepted the 1100-deep valid array (older parsers may reject it), so
  the portable test asserts failed health and separately injects parser recursion.
- Browser redirect hops could bypass the initial route-origin guard. Approved
  resources now use route.fetch(max_redirects=0), reject 3xx before following and
  fulfill only nonredirect responses. A seventh real-browser test verified zero
  requests to a forbidden redirect destination. See official API behavior:
  https://playwright.dev/python/docs/api/class-route#route-fetch
- Navigation errors now retain the failing phase; screenshot-directory failures
  cannot stop the probe. Full-page masking remains enabled for optional screenshots.

Seven browser fixture cases passed after these corrections. Final unittest
discovery passed **194 tests** in 62.768 seconds. The final approved development
check also passed live/ready/UI shell, blocked one session POST, and retained one
optional-resource failure without failing the check. Final owned-process drill
also passed all 15 groups with exact event counts; every owned process/server
was stopped and temporary databases removed. Source-excerpt reviewers accepted
the corrected timeout/parser/redirect/ownership code; they did not execute tests.

Development checks: initial success, a subsequent 15-second UI-shell timeout with
healthy live/ready, then successful bounded repeats. The timeout is retained in
evidence and is not dismissed as uptime success. No production incident claimed.

Stage-6 commit: `7c8ba43`.

## Stage 7 and final audit

Runbook covers standalone installation, one-shot/continuous execution, private
state/logs, thresholds/deadlines, optional masked screenshot, synthetic receiver,
generic webhook schema, stale locks, send-loss semantics and independent-host
supervision. Scoped requirements set Playwright >=1.48 for socket interception,
without changing shared application requirements. Installed HTTPX 0.28.1 and
Playwright 1.64.1 satisfy them; Chrome 157 was actually used.

Final requirement audit is in verification.md. Final code passed seven real-browser
fixture scenarios and all 15 real-process drill groups. Approved development host
final run passed health/loader/frame/UI shell with one blocked session POST.
Independent stage-7 reviewer found no blocker, emphasized preserving the transient
timeout and reporting only synthetic delivery; these limits remain explicit.
Reviewers used supplied excerpts because their tools were unavailable; all actual
execution was by the main agent. No independent execution claim.
Final repeated full suite: 194 tests in 53.466 seconds, native process exit 0.

No changes to application/backend/frontend business logic, session/database/schema,
content, backup tooling, deployment or CI. No keys rotated or Runflare changed.
No push, PR, merge, deployment, production interruption or ongoing alerts/scheduler.

## Subsequent publication authorization and review

User authorized double-check, push and merge after the original local delivery.
Merged current main `80327d1` as `16d9a2d`, preserving PR #20 service wording.
Revalidated: serial full suite 194 passed (78.211 seconds), seven browser cases
passed, corrected real-process drill all 15 groups passed with native exit 0 and
owned-resource cleanup. Fixture startup now waits for actual agent readiness;
monitor deadlines/thresholds and all assertions are unchanged. Initial concurrent
timeouts and the new external development connection/timeout failures are retained
in [publication-review.md](publication-review.md). No current remote-uptime claim.
This checkpoint is ready for branch push and PR merge; no deployment or live-alert
activation is included in the new authorization.
