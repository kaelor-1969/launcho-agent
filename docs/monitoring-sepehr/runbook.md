# Service and widget monitoring

Scope: read-only availability and configured UI shell. See [baseline](baseline.md).
No model call, chat message, session creation, confirmation or draft write is sent
by this monitor. Browser requests other than GET/HEAD, API GETs, third-party origins,
service workers and WebSockets are blocked. Use only approved hosts whose resource
GETs are safe. Existing database/backup monitor remains separate and unchanged.

## Install and check once

Run from repository root, Python 3.11+. A standalone monitoring host needs only:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-monitoring.txt
# If using bundled Chromium instead of installed Chrome:
.\.venv\Scripts\python.exe -m playwright install chromium
```

Config `browser_channel` selects `chrome` (installed Chrome), `msedge` (installed
Edge) or `chromium` (Playwright-managed Chromium). Current verified browser: Chrome.
Socket interception requires Playwright 1.48+; the scoped monitor requirements set
that minimum. Older versions fail closed as `browser_unavailable`. For the real
FastAPI/mock drill and full repository tests, also install `requirements-dev.txt`.

User-confirmed development targets, with mock API environment:

```powershell
.\.venv\Scripts\python.exe scripts/monitor_availability.py --config docs/monitoring-sepehr/config.development.json --once
```

This contacts `https://launchox.ir/` and `https://ag.launchox.ir`. It does not check
`https://launcho.ir`; that is a separate final acceptance target. Config files contain
only public trusted targets. Target query strings/userinfo/fragments are rejected.
Do not derive targets from an HTTP request or customer data. Redirects are failures;
approve and explicitly configure the final URL if the host moves.

`--once` exit codes: 0 all checks currently healthy, 1 one or more checks failed,
2 config/state/lock/runtime error, 130 interrupted. Thresholds govern notifications,
not the per-cycle health exit code. Without `--once`, polling is continuous until
Ctrl+C. No scheduling/service installation was performed in this delivery.

## Reproduce locally

The example JSON uses example ports, not production settings. In separate terminals:

```powershell
.\.venv\Scripts\python.exe tests/monitor_fixture.py --port 8020
.\.venv\Scripts\python.exe tests/monitor_fixture.py --port 8022 --widget-base http://127.0.0.1:8020
.\.venv\Scripts\python.exe scripts/monitor_availability.py --config docs/monitoring-sepehr/config.local-example.json --once
```

Those fixture health responses are synthetic; actual widget files are served.
For the complete drill with real FastAPI and mock API processes, temporary isolated
databases and local webhook receiver:

```powershell
.\.venv\Scripts\python.exe tests/monitor_outage_drill.py
.\.venv\Scripts\python.exe tests/monitor_widget_browser.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_monitor*.py" -v
```

The drill never stops pre-existing services. It launches and stops its own process
handles and temporary servers. It does not send chat/confirmation operations. Its
outage threshold is two samples to keep the drill short; default config uses three.
Before a healthy/restarted-agent scenario, fixture startup waits for the real
`/health/ready` response; the root greeting is only liveness. This setup wait does
not change the monitor's per-check deadline or incident thresholds.

## Configuration and logs

| Setting | Default/example | Meaning |
| --- | --- | --- |
| service_url | explicit origin | GET `/health/live` and `/health/ready`, exact JSON status |
| host_url | explicit full host page URL | real browser navigation; exact URL, no redirects |
| loader_url | explicit `/widget/loader.js` | exactly one matching host script and successful loader response |
| label | local-example / external-host | separates fixture and remote host evidence |
| timeout | 10 s local, 15 s development | total deadline per HTTP request, per browser launch and per UI inspection; delivery attempt deadline |
| interval | 60 s | delay **after** complete cycle, not fixed start-to-start cadence |
| failure_threshold | 3 | consecutive failing samples per check to open an incident |
| recovery_threshold | 2 | consecutive successful samples per check to recover |
| delivery_attempts | 2, maximum 3 | attempts per transition; short bounded backoff |
| state_file | artifacts/monitoring/...json | private monitor-owned state; persistent volume for continuous use |
| browser_channel | chrome | installed browser or managed chromium |
| screenshot_dir | empty | disabled; if set, fixed failure filename, entire page masked |

Checks run serially and never overlap in one instance. One cycle can take two HTTP
deadlines plus browser launch/inspection/cleanup and up to three delivery sequences.
Browser startup, automation and OS cleanup add overhead; this is not a hard real-time
SLA. No HTTP probe retries. Alert retries have the same event ID; receivers should
deduplicate that ID. HTTP 2xx acknowledges delivery; response bodies are not logged.

JSON lines go to stdout; errors use sanitized event codes. Example local log:

```powershell
.\.venv\Scripts\python.exe scripts/monitor_availability.py --config docs/monitoring-sepehr/config.development.json > artifacts/monitoring/development.log
```

Create the output directory first. Tests/drills create `artifacts/monitoring/`.
Logs/state/screenshots/startup logs are ignored by Git. Screenshots are intentionally
fully masked, so counters and phase codes are the useful diagnostic evidence. No
page text, exception stack, response body, token or webhook URL is persisted by the
monitor. Current module-stack attribution assumes widget scripts under `/widget/`;
review that rule if the frontend asset layout changes.

## Alert channel

No actual channel has been selected. The implemented transport sends a generic JSON
POST; it is not a Slack/Telegram-specific payload adapter. Choose an approved receiver
which accepts this schema, or have the channel owner provide an adapter.

- `LAUNCHO_MONITOR_WEBHOOK`: private destination URL, HTTPS except loopback tests.
- `LAUNCHO_MONITOR_WEBHOOK_TOKEN`: optional printable ASCII Bearer token.

Supply these securely in the process environment; never add them to JSON, Git,
command history, chat or docs. The script does not load `.env`. Default is dry-run
and makes no webhook request. Once the channel is chosen, one explicitly labelled
test can be run with an approved environment:

```powershell
.\.venv\Scripts\python.exe scripts/monitor_availability.py --config docs/monitoring-sepehr/config.development.json --send --test-alert
```

`--test-alert` sends one آزمایشی/test payload and exits, without probes/transitions.
It does not prove the destination rendered a message; verify with the channel owner.
Use `--send` for actual transition delivery only when operations authorize activation.
No ongoing external delivery was enabled here. Synthetic receiver delivery and
dry-run tests are distinct from actual channel delivery.

Transition payload includes id, UTC time, outage/recovery type, live/ready/widget
check, public target origin, label, safe error code, summary and all check statuses.
Widget summary always states UI shell only; session verification is false. A full
service outage can produce three events (live, ready, widget), each once per incident.

## Restart and incident handling

State persists capped streaks and open/closed incident status per target identity.
One outage transition is emitted at the failure threshold and one recovery at the
recovery threshold. No reminders or cooldown resends. A transient below the threshold
resets on the next success. Restart retains streaks, including an open incident.

State is atomically replaced **before** delivery. A crash between save/send, or
exhausted attempts, can permanently lose a notification; no replay/outbox is provided.
Within a sequence, a lost acknowledgment can cause duplicates; deduplicate by id.
Atomic replacement is not a power-loss durability guarantee (no fsync). Monitor
state deletion intentionally starts fresh and can repeat an ongoing outage alert.

Exclusive `.lock` alongside the state prevents two CLI instances using that state.
After a hard kill, inspect the recorded PID **and command identity** before removing
only the stale monitor lock. Never remove a live instance's lock. Different state
files can still produce duplicate alerts: run one owner per configured target set.
The application database is never used for monitor state.

- `http_status`: inspect proxy/backend status, including 3xx; never treat login HTML
  or a redirected success page as healthy.
- `content_type`, `invalid_json`, `health_contract`: verify the deployed endpoint
  and version; do not weaken the health contract to silence the incident.
- `timeout` / `connection`: verify DNS, TLS, routing and service process from the
  independent monitoring host. TLS verification remains enabled; proxies are ignored.
- `loader_timeout`, `iframe_*`, `ui_shell_*`: check actual embed URL, CSP, frame-ancestors,
  sandbox and module errors. Nonzero optional failures alone do not cause an outage.
- `browser_unavailable`: install the chosen browser and compatible Playwright; a
  monitor-environment failure may be the cause rather than a broken site.
- `alert_delivery_failed`: polling continues; repair destination/credentials privately,
  then run one labelled channel test. Failed transition alerts are not replayed.
- `monitor_error`: inspect trusted config/JSON types, target identity, state permissions,
  disk and lock. Corrupt/mismatched state is not silently discarded. Repair or archive
  privately and choose a new state file deliberately. State persistence errors stop
  the monitor before sending; supervise the monitor process itself.

For recovery require the configured consecutive successes for the affected checks;
one successful sample is insufficient. A healthy shell does not clear backend ready
failures and cannot validate adapter/model work.

## Hosting preparation for Parsa

Run one monitor process on a host independent of the service being monitored. Use
a private persistent state volume, fixed working directory and restricted environment
and logs. Install browser OS dependencies on that host; use normal browser security
and do not run Chromium as root with sandbox disabled. Approve its outbound HTTPS
and target CSP. Protect/rotate logs and limit access to monitor state and credentials.

Suggested supervision: a foreground continuous command managed by the host's normal
service manager, with restart-on-failure and bounded restart delay. Alternatively run
`--once` periodically using the same persistent state; ensure the scheduler prevents
overlap and interprets exit 1 as a check failure. Neither option has been installed
or enabled. Do not schedule more often than the worst-case full-cycle duration.

A monitor on the same host cannot independently report complete host/network loss.
Move this exact CLI/config to an approved independent host for that coverage; this
handoff creates no external infrastructure, accounts or subscriptions. Parsa owns
Runflare setup; no Runflare settings changed. Dina owns production adapter/catalog
correctness and complete operation recovery. Provider owner owns key rotation.
