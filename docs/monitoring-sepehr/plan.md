# Monitoring plan — 2026-11-14

Baseline: `b4c0091` on `main`; clean working tree. Work branch:
`work/monitoring-sepehr`. Remote is GitHub `kaelor-1969/launcho-agent`.
No applicable AGENTS.md was found in this checkout or its ancestor directories.
Existing reports are historical: parsa-operations describes another checkout and
ports; none of those processes, URLs or credentials are assumed active here.

Each stage uses inspection, implementation, primary diff review, a fresh independent
reviewer, actual validation and a local commit. No push, PR, merge or deployment.

| Stage | Acceptance | Status |
| --- | --- | --- |
| 1 baseline | Trace health and UI readiness to code; state limits and ownership | complete |
| 2 HTTP | Configurable GET checks reject redirects, bad JSON/status, timeout and connection errors; bounded, serial execution | complete |
| 3 widget | Real browser on two origins; loader, one frame, configured visible UI; failures tested; zero outgoing writes | implemented; local/development verified, transient timeout recorded |
| 4 incidents | Failure/recovery thresholds, one transition event, durable restart state, bounded delivery | complete locally |
| 5 channel | Environment-only generic webhook, dry-run and controlled receiver tests; approved real channel if supplied | complete synthetic; real channel unselected |
| 6 drill | Owned local process outage/restart, transient and widget-only faults, sender failures and restart | complete, final-version repeat passed |
| 7 handoff | Runnable manual/continuous commands, operations and dependency guidance; two final verification rounds | complete; no operational activation |

Existing `scripts/monitor_backend.py` owns backups/disk checks and stays unchanged.
The availability tool will reuse the live/ready contracts without importing the
application or accessing its database. This is the alert/browser layer missing
from the existing tool, not a replacement backup system.
