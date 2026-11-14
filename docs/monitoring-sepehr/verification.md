# Verification evidence — 2026-11-14

All commands run locally on Windows with the repository `.venv` Python, real
installed Chrome and normal browser security. Independent reviewers had no file or
execution tools; they reviewed supplied code/evidence only. Main agent executed
the tests. No independent test execution is claimed.

## Requirement audit (round 1)

| Requirement | Implementation/evidence |
| --- | --- |
| Exact health meanings, limits | baseline.md, existing app/main.py routes |
| Timeout, non-2xx/redirect, HTML, JSON and connection checks | probe_health; HealthTests |
| Trusted config, finite validation, no secret output | Config/valid_url, controlled invalid-config tests, safe event fields |
| Real host loader/frame/usable shell | probe_widget; normal Chrome; visible configured frame, editable message control, enabled working close |
| Cross-origin security unchanged | two-origin fixture tests and actual development host; no disable-web-security flags |
| No business operations | browser pre-navigation GET/HEAD-only routing, API GET blocked, no text submitted; six fixture tests observe zero outgoing writes |
| Essential vs optional failures | resource-type rules; image404 remains healthy; loader/frame/module faults fail |
| Safe screenshots | disabled by default, optional full-page mask; code/counters retained instead of customer pixels |
| Transient/persistent and confirmed recovery | per-check streaks; threshold tests and real process drill |
| No repeated incident alerts across restart | atomic private state, identity validation, no replay/reminders; restart after each drill sample |
| Bounded sender failure, monitor continues | local receiver 503/302/timeout/refused-connection tests; failure drill |
| Unknown actual channel | user explicitly selected synthetic receiver; env interface and dry-run implemented |
| Owned outage resources only | drill owns Popen handles and temporary databases; finally terminate/wait and server/thread cleanup |
| Existing backup monitor untouched | no changes scripts/monitor_backend.py or application/session/database code |
| Operations guidance and dependencies | runbook.md and dependencies.md; no external infrastructure or activation |

Shell readiness is deliberately narrower than a working authenticated conversation.
The deployed widget automatically POSTs to create a session; the monitor blocks it.
No session response is mocked into the monitored page. Full usability of message
submission cannot be accepted under the no-write constraint; backend-owner contract
work would be needed for a read-only conversation-readiness guarantee.

## Executed results

- Full repository unittest discovery: **194 tests passed**, final repeat 53.466 seconds, zero
  skipped tests in the reported run. `test_ai.py` at repository root was not run.
- New HTTP tests: 6 passed; incident tests: 5 passed; webhook tests: 5 passed.
  Existing backup-monitor tests were included in the full suite without changes.
- Seven actual Chrome fault scenarios passed: healthy, loader503, frame503, missing
  readiness, JS exception, optional image404 and forbidden redirect. Every local fixture observed zero
  outgoing non-GET requests; redirect destination observed zero requests. Healthy
  cases observed one blocked session POST.
- Real FastAPI + local mock API outage drill passed 15 observations/assertion groups:
  transient0 alerts; persistent outage3 alerts (live,ready,widget); continued outage3;
  confirmed recovery6 total; widget-only outage7 with health still good; widget
  recovery8; rejecting receiver6 bounded attempts for three transitions and no
  replay; CLI labelled channel-test1 message to synthetic receiver.
- Actual user-approved development targets: both health contracts and Chrome
  loader/frame/UI shell passed on launchox.ir/ag.launchox.ir. One session POST was
  blocked; no session verification. One optional-resource failure did not cause
  failure. HTTPS and normal browser security remained enabled.
  A later concurrent verification run observed `ui_shell_timeout` within 15 seconds
  while both health endpoints passed; the subsequent bounded repeat passed all
  three checks. This is evidence of a transient loading timeout, not stable uptime
  or production readiness. Both outcomes are retained locally.

Raw JSON/log evidence is intentionally untracked in `artifacts/monitoring/`:
`browser-results.json`, `drill-results.json`, `unittest-final.log`,
`development-check.jsonl` and corresponding console logs. No secrets are included
in this committed summary. Test databases were temporary and removed.

## Final-version verification (round 2)

Repeated the real-browser fault suite (seven passed), real-process outage drill
(all 15 groups passed) and one-shot approved development check (all checks passed)
after final timeout/parser/redirect/fixture startup corrections.
Full unittest discovery passed 194. Final results are recorded in progress.md.
No periodic task or alert channel has
been activated. Main-domain launcho.ir acceptance remains outside this execution.
