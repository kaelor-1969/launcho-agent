# Remaining dependencies

- Sepehr/operator: approved real host URL and widget service origin; approved
  alert destination and credentials in environment (never in Git/chat/logs).
  Repository inspection found no configured alert channel. No destination guessed.
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
