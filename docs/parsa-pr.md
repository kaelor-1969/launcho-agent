# Harden backend runtime and persistent session operations

The local agent had no scheduled session cleanup, operational backup/restore tool, readiness probe, configurable embedding policy or request admission limits. This change adds those controls while preserving the session, preferences, review and confirmation API bodies.

Production rejects local mock configuration and requires an absolute session database path and explicit iframe host origins. Render is configured for one instance with persistent storage and live draft writes disabled. The local launcher supports independent ports and noninteractive serving. CI defines Windows, macOS and Linux checks plus a Docker build.

Validation on Windows: 90 Python tests passed, including unknown-result recovery after core restart, backup/restore and retention; JavaScript session checks passed; both shop and website flows passed against running local HTTP services. No real model or Launcho API was called. Docker, CI, macOS and external deployment have not run in this environment.

Base: baseline/local-delivery-2026-11-13 (694c4b9). Head: work/parsa-backend. Operational instructions and remaining external dependencies: docs/parsa-operations.md. The common baseline must be published before opening the backend PR against it; the existing origin points to a local directory, not GitHub.
