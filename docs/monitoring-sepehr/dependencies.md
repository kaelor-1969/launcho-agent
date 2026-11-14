# Remaining dependencies

- User confirmed development/mock environment: `https://launchox.ir/` host and
  `https://ag.launchox.ir` widget/API. Initial read-only HTTP and browser checks
  passed on 2026-11-14; no non-GET/HEAD browser requests were allowed through.
  `https://launcho.ir` belongs to final acceptance and was not checked here.
- Sepehr/operator: choose approved alert channel; user explicitly requested a
  synthetic receiver until then. Supply `LAUNCHO_MONITOR_WEBHOOK` and optional
  `LAUNCHO_MONITOR_WEBHOOK_TOKEN` in the process environment. No channel guessed.
- Parsa: provision an independent monitoring host with Python, Playwright/Chromium,
  outbound HTTPS, read access to the approved host, persistent private monitor
  state directory and restricted logs. Configure CSP frame-ancestors for that host.
  Choose service supervision, log retention and availability. No Runflare changes
  or scheduler activation performed here.
- Dina: production catalogs/options, adapter endpoints, model evaluation and full
  operation recovery remain outside availability/UI-shell monitoring.
- Provider account owner: key rotation and account limits; no keys rotated here.

Without a session POST, conversation readiness cannot be verified. This delivery
checks configured usable UI shell, not enabled message submission or successful
session initialization. A future read-only session health contract, if desired,
requires the backend owner's design; this task does not invent it.
