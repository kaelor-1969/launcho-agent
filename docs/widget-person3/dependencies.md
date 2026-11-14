# Dependencies outside ownership

- Production catalog-backed form is unavailable: `app/api/routes.py` restricts `/api/local-signup-options` to `local_mock`; widget.js initializes this form only in that mode. Keep the existing demo warning. A production options contract/delivery is backend-owned.
- Production adapter compatibility and draft creation are not verified by controlled frontend tests. Do not infer production readiness.
- Durable refresh recovery of unknown confirmation requires an agreed credential/pending-operation retention policy or server recovery contract. Current credentials and pending review are memory-only; do not silently persist tokens or create replacement operations.

- Catalog evidence: 25 visible samples but only 23 preview links; khodro (source title has a spelling issue) and danesh lack URLs. One hidden boutique row excluded intentionally. Website sample has no preview. All 23 shop URLs were reachable and rendered in Chrome smoke checks; official registration availability remains unverified.

- Refresh protection is best effort: host beforeunload warns while confirmation is pending, and UI says not to refresh. It cannot survive forced close/mobile termination, iframe-only reload, or an accepted unload. Memory credentials are intentionally not persisted; after forced refresh the original pending confirmation cannot be recovered. Do not claim durable replay or production readiness.
