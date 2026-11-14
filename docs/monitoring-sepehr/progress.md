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
