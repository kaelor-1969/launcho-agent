# Dependencies outside ownership

- Production catalog-backed form is unavailable: `app/api/routes.py` restricts `/api/local-signup-options` to `local_mock`; widget.js initializes this form only in that mode. Keep the existing demo warning. A production options contract/delivery is backend-owned.
- Production adapter compatibility and draft creation are not verified by controlled frontend tests. Do not infer production readiness.
- Durable refresh recovery of unknown confirmation requires an agreed credential/pending-operation retention policy or server recovery contract. Current credentials and pending review are memory-only; do not silently persist tokens or create replacement operations.
