# Handoff

Branch `work/monitoring-sepehr`; baseline `b4c0091`; validated implementation HEAD
`7c8ba43`. This handoff is part of the final documentation commit on top of that
implementation; resolve its exact HEAD with `git rev-parse HEAD` / `git log -7 --oneline`.
Initial tree was clean. Before the final documentation commit, only runbook,
verification summary, monitor requirements and these checkpoint updates remained.
After that commit the expected tree is clean; ignored artifacts are not deliverables.

All seven implementation/local-test/documentation stages complete within requested
scope. Actual channel unselected: user requested synthetic delivery. Final acceptance
on `https://launcho.ir` and operational activation remain outstanding owner tasks.

Actual tests: six HTTP, five incident, five delivery tests; full unittest log 194
passed; seven Chrome fault scenarios; final actual FastAPI/mock 15-group outage drill
passed after timeout/parser/redirect fixes. Every owned subprocess/server stopped
and temporary DBs removed. Source reviewers had no tools, reviewed supplied excerpts;
no independent test execution claimed.

User-approved development launchox.ir/ag.launchox.ir final check passed HTTP live,
ready, loader, frame and UI shell. Automatic session POST blocked, session not
verified. Earlier 15-second shell timeout with healthy HTTP retained in evidence;
no stable uptime claim. No launcho.ir check performed.

Next precise owner actions: choose approved generic JSON webhook/adapter, inject
LAUNCHO_MONITOR_WEBHOOK and optional LAUNCHO_MONITOR_WEBHOOK_TOKEN securely, run one
labelled channel test, then authorize Parsa to provision an independent host/private
state volume/supervision/CSP. See runbook.md and dependencies.md. Do not activate
continuous sends or alter Runflare under this handoff alone.

To resume: read plan.md, progress.md, verification.md and runbook.md, inspect Git
status/HEAD, preserve commits and apply only the explicitly requested owner follow-up.
No push, PR, merge, deployment, key rotation or production outage performed.

## Later publication checkpoint

User subsequently authorized push and merge after a double-check. Main `80327d1`
was incorporated as `16d9a2d`. See publication-review.md for the completed repeated
194-test suite, seven Chrome cases, 15-group drill, fixture readiness correction
and observed external development failures. This source checkpoint precedes the
authorized push/PR merge; use Git/GitHub for its final publication commit and PR.
The previous no-push statements describe earlier delivery only. Operational
activation, real alert channel and launcho.ir acceptance remain outstanding.
