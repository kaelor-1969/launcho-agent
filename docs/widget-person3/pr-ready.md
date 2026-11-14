# PR preparation

Suggested title: **Protect unresolved widget confirmations and verify the complete frontend flow**

Publication base: origin/main96cc945883b80487afe1cefadc7731cd29ef4435; branch work/widget-person3-reviewed. Original branch and6ff86df preserved, Python cache commit excluded. See prepush-review.md.

When a confirmation response is lost, the widget now clearly identifies the unknown result, retains the same review for manual retry, and asks the host to warn before refresh. The iframe sends only pending/resolved flags through its existing validated channel. Temporary adapter unavailability keeps an unresolved review locked. Expired reviews require a new manual review, and a status response reporting expiry disables the old continuation link. Status checks display progress and suppress duplicate GETs.

Existing shop/website forms and the current appearance are preserved. New controlled tests cover native double-click, browser offline transport, a truncated confirmation response after acceptance, exact retry identities, refresh, hostile continuation links, iframe message gates, loader timeout, status/error recovery, keyboard navigation, accessible control names and reduced motion. Every one of the 23 shop previews and category recommendations is checked; a separate read-only public audit records HTTP and browser rendering smoke results.

Validation: `node tests/widget_quality_check.cjs`; stage-7 full signup suite also passed in Edge. Exact results and limitations are in progress.md and browser-coverage.md. Screenshots/reports: evidence.md. Public catalog results are snapshots, not production compatibility evidence.

External blockers: production options delivery, official adapter/registration verification, missing public/website previews, and a durable unknown-result recovery/retention contract. No Python, route, schema, backend fixture, adapter, AI-service or content files were modified. No credentials were persisted. No production model/signup/payment calls, push, PR creation, merge or deployment were performed.

Reviewer should inspect the frontend changes in stages 5–6 and the complete diff against the baseline. Full WCAG, Safari/Firefox and physical-device certification remain outside observed coverage. The user authorized only publication of this dedicated branch after both review rounds pass. No PR, force push, merge or deployment is authorized.
