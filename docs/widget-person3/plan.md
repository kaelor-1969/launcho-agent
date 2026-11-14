# Widget person 3 â€” acceptance and status

Local baseline: `6ff86df9ab5c4f4f23556147f4f330cf7cfd07a3`, clean `main`.
Branch: `work/widget-person3-quality`. Shared team baseline is unverified.
Scope: frontend and JavaScript/browser tests; documentation only here. No backend/catalog changes.
No AGENTS.md found in repository or inspected ancestor directories.

| Stage | Acceptance / files | Status |
| --- | --- | --- |
| 1 | Existing shop/website forms retain all choices, edit invalidates approval, Persian review, native keyboard; widget_signup_browser.cjs | Complete locally; production options blocked |
| 2 | Count actual catalog entries, exercise every selectable preview, record missing/broken data without altering content | Complete audit; catalog gaps recorded |
| 3 | Native double activation produces one request, synthetic approval rejected, pending controls locked | Complete locally |
| 4 | Browser transport disconnection and lost response; explicit retry preserves chat requestId and confirmation body | Complete locally |
| 5 | Safe expiry/errors/unknown outcome and refresh, no automatic confirmation or browser credential persistence | Pending |
| 6 | Approved continuation destination, status retry/lock, lazy iframe and loader lifecycle | Pending |
| 7 | Desktop/mobile/short viewport, keyboard/focus/accessibility, report actual browser coverage | Pending |
| 8 | Regression tests, committed visual evidence, installation and PR handoff | Pending |

Each stage: inspect, smallest coherent change, diff review, fresh independent reviewer, actual tests, scoped commit, update handoff. Controlled fixtures never establish production compatibility.
