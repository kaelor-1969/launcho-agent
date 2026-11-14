# Publication review — 2026-11-14

The user subsequently authorized double-checking, pushing and merging this work.
This supersedes the initial delivery's no-push/no-merge instruction. Deployment,
Runflare changes, key rotation, continuous alerts and main-domain acceptance are
still outside this action. Earlier reports describe their original checkpoints.

Before publication, working tree was clean at `7ad10c4`. Fetched latest origin/main
`80327d1` (PR #20, coming-soon service wording) and merged it without conflicts as
`16d9a2d`. Original commits and the upstream change are preserved.

Primary source review covered HTTP deadlines/contracts/response bounds, routing
and redirect policy, no outgoing writes, UI-shell scope, thresholds, private state,
locking, bounded delivery and secret-safe logs. Changed-file review against current
main includes only monitor scripts/dependencies, tests/fixtures and dedicated docs;
application, database, frontend business logic and deployment files are unchanged.

Revalidation is performed against the merged code. An initial concurrent run
observed a four-second UI-shell timeout in the drill and a 20-second subprocess
timeout in an existing mock-draft test. These failures are retained; tests and
thresholds were not weakened. The first isolated drill also caught a readiness
timeout after restart: fixture startup had checked only the root liveness greeting.
Startup now checks `/health/ready` for the agent before asserting healthy scenario
preconditions; the mock still uses its root. Monitor timeouts/thresholds and every
scenario assertion remain unchanged. This adds only read-only setup requests.
The setup request budget is five seconds within its existing 30-second startup
window: a direct local readiness diagnostic measured 1.39 seconds, exceeding the
first one-second setup budget. Abandoning those requests early could leave repeated
setup checks executing. Direct mock options/pricing returned HTTP 200; the real readiness probe
also returned HTTP 200 when allowed to complete. No product endpoint was changed.

Seven Chrome fault cases passed, including zero outgoing writes and zero requests
to the forbidden redirect receiver. A new development-host sample observed health
connection/timeout errors and host-navigation timeout; this supersedes any claim
of current remote availability. Prior successful samples remain historical only.
Actual alert channel is unselected; all delivery testing uses local synthetic
receivers. Session/model/business readiness and launcho.ir acceptance are excluded.

## Final local results

- Full repository unit suite, run serially: **194 passed**, 78.211 seconds, native
  exit 0. No test was skipped or weakened; the initial subprocess timeout was not
  reproduced in the serial run.
- Real Chrome fault suite: **seven passed**, zero outgoing writes and zero requests
  reaching the forbidden redirect server.
- Corrected isolated real-process drill: **all 15 groups passed**, native exit 0.
  Exact outage/recovery counts, widget-only failure, bounded rejected deliveries,
  restart without replay and one labelled CLI test passed. All owned subprocesses,
  local servers and temporary databases were cleaned up.

No publication has been performed at this checkpoint; PR/merge outcome is reported
separately. Ongoing monitoring/real alerts remain inactive.
