# Local double-check — 2026-11-15

Scope: commits `e463888` and `d864e66`. Initial working tree clean. Re-read the
CLI tests, receiver lifecycle, monitor transport/CLI implementation and current
Runflare/dependency/handoff documentation. `git diff HEAD~2 HEAD --check` passed.
No application changes, external probes, production DB/backup access, support
messages, push or deployment.

## Actual execution and retained failures

First ran monitoring unittest discovery concurrently with the Chrome fixture
script. Browser completed all seven scenarios, native exit 0, zero outgoing writes
or forbidden redirect requests. The unittest run completed **23 tests with two
failures**, 51.618s, native exit 1:

- `HealthTests.test_rejects_status_redirect_html_and_invalid_contract`, an
  `http_status` subcase: expected `http_status`, received `timeout` (2s deadline).
- `MonitorCliTests.test_failed_receiver_has_bounded_retries_and_failure_exit`:
  expected two receiver POSTs, observed one. The preceding exit-1 assertion
  succeeded. Two configured attempts do not guarantee two received requests;
  an attempt can time out before reaching the receiver.

After both processes ended, reran the identical monitoring suite serially:
**23 passed in 41.167s**, native exit 0. No code, timeout, threshold or assertion
was changed. Concurrent load is a hypothesis for the difference, not a verified
root cause. Concurrent test stability remains unverified; the earlier failures
are not considered fixed or erased by a successful serial run.

Then repeated each affected test three times serially with the same settings:
**six test executions passed in 31.907s**, native exit 0. This reduces concern
about immediate serial reproducibility but does not establish concurrent stability.

Reproduction (repository root; run one command to completion before the next):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_monitor*.py" -v
.\.venv\Scripts\python.exe tests/monitor_widget_browser.py
```

The monitoring discovery includes three existing backend tests, which create only
synthetic SQLite and backups inside `TemporaryDirectory`; no production path is
used. The Chrome fixture imports no application backend and blocks session writes.

## Review and operational limits

Fresh Subagent review was limited to supplied evidence/excerpts because it lacked
file/command tools. It found no additional substantive mismatch and recommended
retaining failures, repeating both affected cases serially and not claiming a fix
without diagnosis. No independent execution or direct commit inspection claimed.

The documentation matches current behavior: dry-run default, environment-only
webhook, no proxy environment, no redirects, persistent-state-before-send, no
failed-event replay, same-state lock and health exit distinct from delivery result.
Real receiver selection and authorized secret entry remain dependent; actual
channel test, hosting/activation and final production acceptance are unperformed.
If Runflare cron is selected, its effective timezone remains for Parsa to confirm.
No provider behavior, account state or timezone was newly verified.
