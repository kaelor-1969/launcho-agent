# Draft destination validation — demo release

The previous validator accepted any HTTP/HTTPS draft destination without credentials, including `https://fake-site.example/login`. This is an incomplete destination check, not evidence of an existing compromise.

The draft validator now accepts exactly one absolute URL: the bundled `draft-preview.html` resolved relative to `workflow-api.js`. Scheme, host, port and path must match exactly. Query strings, fragments, credentials, relative URLs, encoded paths and noncanonical spellings are rejected. Neither the service response nor workflow endpoint configuration can expand this allowlist. Real signup destinations require a separately reviewed contract and allowlist.

Validation on 2026-11-08:

- Chrome workflow checks passed at widths 1280, 390 and 320, including editing all four choices, explicit confirmation and opening the labeled static preview.
- All 18 additional untrusted destination cases were rejected by both schema validation and mocked service responses. The UI displayed no draft link for these responses and recovered when the service returned the allowed URL.
- All 52 invalid/legacy schema cases were rejected. All three subscription periods passed. Confirmation retries kept the same idempotency key.
- A browser regression control confirmed that the previous validator accepted the fake-site URL and the fixed validator rejected it.
- Full backend unittest discovery could not run: dependencies are absent and installation timed out downloading FastAPI metadata from files.pythonhosted.org. No backend implementation changed in this fix.

Reproduce with `python tests/widget_preview_server.py --port 8000`, then `python tests/widget_workflow_browser.py --base-url http://127.0.0.1:8000`. The browser runner uses installed Chrome and mocks service responses; it makes no real signup or AI requests.

This is a clearly labeled demo. Merging it into `main` does not certify real signup integration or readiness for final customer release. Existing session integration, production deployment and device testing limitations remain in [the delivery report](widget-delivery.md).
