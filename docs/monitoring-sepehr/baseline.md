# What health means

Source: `app/main.py` at baseline `b4c0091`.

- `GET /health/live`: HTTP 200 with JSON `status: ok`; process responds.
- `GET /health/ready`: HTTP 200 with JSON `status: ready`; opens a session-store
  transaction, reads sessions, and calls `core.data('shop')`. Exceptions produce
  HTTP 503 with `status: not_ready`. Adapter mode is informational.
- `GET /` is only a process greeting; it is not readiness.

Neither endpoint proves model correctness, production catalog correctness,
adapter writes, complete recovery, customer signup or payment. Ready can depend
on Dina's catalog/adapter work. No new business endpoint is needed.

`frontend/loader.js` mounts `#launcho-widget` with an open shadow root. It creates
the iframe when opened (the current default is auto-open, despite older README
wording). It authenticates the ready/configured handshake using origin, source,
scope and a random channel. Only configured makes the frame visible.
`frontend/widget.js` sends ready after module setup and configured after accepting
configuration. Real configuration automatically initializes a session with POST.

Browser monitoring will observe the existing visible-frame handshake and actual
rendered `#message`/`#close` controls through Playwright's normal cross-origin frame
automation. It must block all non-GET/HEAD requests before navigation, service
workers and sockets. It will never submit text or create/confirm a draft. Session
creation is deliberately blocked and is reported separately. UI shell readiness
is not authenticated conversation readiness. No product behavior is changed.

Local fixture hosts will embed the real loader from another loopback origin.
They are test infrastructure only. Synthetic health failures and resource faults
belong to these fixtures, never product endpoints. Production-host success and
real-channel delivery require explicit approved destinations.
