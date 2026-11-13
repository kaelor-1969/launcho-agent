# Harden backend runtime and persistent session operations

The local agent had no scheduled session cleanup, operational backup/restore tool, readiness probe, configurable embedding policy or request admission limits. This change adds those controls while preserving the session, preferences, review and confirmation API bodies.

Production rejects local mock configuration and requires an absolute session database path and explicit iframe host origins. Render is configured for one instance with persistent storage and live draft writes disabled. The local launcher supports independent ports and noninteractive serving. CI defines Windows, macOS and Linux checks plus a Docker build.

Validation includes 92 Python tests, real HTTP shop and website flows, startup failure diagnostics, occupied ports, backup and restore, and unknown-result recovery after restart. CI runs on Windows, macOS and Linux and builds and exercises Docker containers, persistent session and draft replay after restart, and staging Compose healthchecks. See the GitHub Actions results for final run status. External production hosting and official Launcho API validation remain dependent on the deployment destination and API access.

The local launcher also supports backend-only verification, persistent data directories and startup log files. The staging Compose configuration runs the agent and local test adapter with separate persistent volumes. The common baseline is PR #13 and the backend changes are PR #14. Base is baseline/local-delivery-2026-11-13 (694c4b9) and head is work/parsa-backend. Operational instructions are in docs/parsa-operations.md.
