# Runflare monitoring preparation — 2026-11-15

Status: **dependent / not activated**. This is a preparation checklist and an
unsent support request, not a statement of current Runflare capabilities. No
account inspection, support contact, secret entry, scheduler change or deployment
was performed. The account observations in `../parsa-finalization.md` are historical
(2026-11-14); recheck them before relying on them. Never mount or access the
production database/backup volume for this availability monitor.

## Dependencies and acceptance evidence

| Item | Status | Owner | Evidence needed to close |
| --- | --- | --- | --- |
| Real alert receiver/adapter | dependent | Sepehr / channel owner | Approved destination accepts generic JSON schema in runbook; channel owner verifies rendering |
| Secret entry | dependent | Person with account access | Secure environment injection of `LAUNCHO_MONITOR_WEBHOOK` and optional `LAUNCHO_MONITOR_WEBHOOK_TOKEN`; no values in Git/chat/logs |
| Real labelled channel test | not performed; dependent on both above | Channel owner + operator | One approved `--send --test-alert`, receiver acknowledgement and visible test message checked; no ongoing sends implied |
| Hosting/runtime | dependent | Parsa + Runflare support | Confirm independent host, browser support, egress, private persistent monitor state and supervision below |
| Cron timezone | dependent **if cron is chosen** | Parsa | Provider-confirmed effective timezone/IANA identifier, how it is configured, and next-run examples in UTC and agreed local time |
| Schedule/activation | not performed | Parsa | Confirmed cadence, overlap/retry/time-limit policy, config/state paths, owner approval and monitored test run |
| Final production acceptance | not performed | Responsible environment owner | Separate approved target/acceptance; synthetic fixtures do not establish production readiness |

No timezone is inferred from developer-machine time, client timezone, server `TZ`
or a cron expression. Parsa must record the provider's answer and the actual
schedule before cron activation. If a continuous supervised process is selected,
cron timezone is not applicable; it remains an unselected option until that choice.
Monitor timestamps are UTC regardless of scheduler timezone.

## Questions to Runflare support (draft; not sent)

Parsa should obtain explicit answers for the selected plan/project:

1. Can an independent monitoring workload run separately from the monitored
   service/failure domain? Does cron depend on the application container being up?
   What coverage is lost during a project, region or provider outage?
2. Is a Python 3.11+ foreground service supported, including restart-on-failure,
   restart delay, termination grace and process health/stale-run detection? Confirm
   billing, resource limits, sleep/scale-to-zero behavior and single-instance control.
3. Can Playwright and its matching Chromium plus OS dependencies be installed?
   Confirm writable temporary storage, browser sandbox/non-root support, process
   and memory limits and startup behavior. Do not solve this by disabling sandbox.
4. Is private persistent storage supported for monitor JSON state and its lock,
   retained across cron invocations, restarts and deployments? Confirm mount path,
   ownership/UID, atomic same-directory rename, permissions, size/cost and retention.
   This is separate monitor storage; no production DB or backup volume is required.
5. For cron: what is the effective timezone and supported configuration mechanism?
   Is it per job/account/project, does `TZ` affect scheduling, and how are DST,
   missed runs, catch-up, retries and overlaps handled? Supply next-run timestamps.
6. What are cron maximum runtime, interval granularity, termination behavior,
   working directory and executable paths? Does exit 1 trigger an automatic retry?
   Can overlap/catch-up retries be disabled and exits 0/1/2 be distinguished?
   Which signal and grace period are used at forced termination, are child Chromium
   processes reaped, and what happens to the next run after an interrupted job?
   A remaining monitor lock requires operator identity/liveness inspection, never
   automatic removal.
7. Can private secrets be injected into both service and cron without putting
   values in command arguments/logs? Confirm access control, rotation/restart
   behavior and log redaction. Ask for mechanisms only; do not send secret values.
8. Is DNS/TLS-verified outbound HTTPS allowed to approved public targets and the
   receiver? Confirm egress allowlists/IP restrictions and CA requirements. The
   monitor ignores proxy environment variables; a mandatory outbound proxy would
   require an explicitly reviewed implementation change.
9. Confirm stdout capture, restricted log access/retention, failed-job visibility
   and an independent missed-run/monitor-process alert. An alert sender cannot
   reliably report its own host outage or broken delivery channel.

Account-specific answers, quoted plan limits, costs and provider references should
be added by Parsa after confirmation. No provider feature/price is assumed here.

## Settings to prepare, not apply

| Setting | Required choice / behavior |
| --- | --- |
| Runtime and working directory | Fixed checkout/release path; install `scripts/requirements-monitoring.txt` and browser dependencies; use absolute Python/config paths in scheduler |
| Targets | Owner-approved service/host/loader URLs in a private reviewed config; local-example ports are fixtures only |
| Browser | Set supported `browser_channel`; use `chromium` only after matching Playwright browser installation; verified local browser is Chrome |
| State | Absolute private `state_file` on monitor-only persistent storage; same path for every invocation for one target set; parent directory owner-only access |
| Screenshots | Disabled unless explicitly needed; masked images still require private storage/retention |
| Secrets | Environment-only webhook URL and optional token, entered by authorized account holder; `.env` is not loaded by this CLI |
| Supervision | Prefer one continuous foreground process with bounded restart delay; otherwise `--once` cron with no overlap; neither configured here |
| Cadence | Continuous `interval` is a delay after completion. Cron starts must allow a full worst-case cycle plus startup/cleanup margin; measure on chosen host |
| Exit handling | `--once`: 0 healthy, 1 checks failed, 2 config/state/lock/runtime error, 130 interrupted. Failed webhook transport is logged separately; cycle exit is health, not delivery success |
| Cron timezone | Unset in this proposal; Parsa must confirm with provider before selecting expression/cadence |
| Security/network | No public inbound monitor endpoint required; approved outbound HTTPS, normal browser security and target frame-ancestors/CSP as required |
| Logs | Private stdout capture/rotation; monitor `alert_delivery_failed`, `monitor_error` and missing runs separately |

For cycle capacity include two HTTP checks, browser launch plus UI inspection,
up to three transition payloads each with `delivery_attempts` bounded request
deadlines/backoff, and browser/process cleanup. `timeout` is not a whole-process
deadline. Provider termination must leave enough cleanup time; hard kills may leave
a stale lock. The same-state lock rejects overlap with exit 2; do not auto-delete it.
Different state paths do not protect against duplicate monitoring of the same target.

Example command shape for Parsa after paths/config/hosting have been confirmed:

```text
<absolute-python> <release>/scripts/monitor_availability.py --config <private-config> --once
```

This is dry-run by default. Continuous supervision omits `--once`. Add `--send`
only after approved channel setup/test and activation authorization. No cron
expression is supplied while timezone and runtime limits remain unconfirmed.

## Local evidence versus remaining work

Local tests use synthetic payloads and an ephemeral `127.0.0.1` receiver. They
verify transport/CLI behavior, not Runflare secret injection, actual notification
rendering, scheduler behavior or production availability. Failed transition sends
are not replayed; persistence-before-send can lose notifications on a crash.
Receivers must deduplicate retry event IDs. These limitations are unchanged.

Parsa records provider answers and schedule evidence; channel owner selects the
receiver and verifies the test; authorized account holder enters secrets. Until
then these items remain dependent. No production DB/backup access, push or
deployment is part of this preparation.
